"""Bounded microbatches, persistent publication, restart reuse and final streaming exports."""

import json
import logging
import shutil
import time
import traceback
from collections import Counter
from pathlib import Path

from app.config import Settings
from app.db import Database
from app.persistence.job_locks import JobContentChanged, check_content_version, job_lock
from app.persistence.progress import ProgressRepository
from app.services.hub_inference import HubSession
from app.services.incremental_export import package_publications
from app.services.inference import NerLabSession
from app.services.model_cache import ModelCache
from app.services.publication import publish, read_publication
from app.services.registry import Registry, model_snapshot, statistics_reference
from app.services.runtime import INFERENCE_MODULES
from app.services.statistics import StreamingStatistics, statistics
from app.storage import LocalStorage, StorageBudget


def process_job(
    job: dict, s: Settings, adapter=None, stats_fn=statistics, registry_factory=Registry
):
    db = Database(s)
    progress = ProgressRepository(db)
    storage = LocalStorage(s.storage_root)
    root = storage.job(job["id"])
    payload = json.loads(job["payload"])
    registry = registry_factory(s)
    models = registry.select(payload["language"], payload["entities"], payload.get("models"))
    snapshot = model_snapshot(models, legacy=payload.get("catalog_version", 1) < 2)
    if payload.get("catalog_version", 1) < 3:
        snapshot = [
            {k: v for k, v in row.items() if k not in ("repository", "revision")}
            for row in snapshot
        ]
    if snapshot != payload["selected_models"]:
        raise ValueError("Model registry changed; resubmit with current model versions")
    rows = [row for row in progress.rows(job["id"]) if row["status"] != "DELETED"]
    if not rows:  # Queued jobs admitted by a pre-v3 API retain their tokens/deadlines.
        from app.visualization.repository import document_id

        with db.connect() as c:
            for name in payload["documents"]:
                c.execute(
                    "INSERT OR IGNORE INTO documents(job_id,document_id,filename,source_type,size_bytes,updated_at) VALUES (?,?,?,?,?,?)",
                    (
                        job["id"],
                        document_id(name),
                        name,
                        "TXT_UPLOAD",
                        (root / "input" / name).stat().st_size,
                        time.time(),
                    ),
                )
        rows = [row for row in progress.rows(job["id"]) if row["status"] != "DELETED"]
    payload["documents"] = [row["filename"] for row in rows]
    from app.persistence.model_progress import ModelProgressRepository

    reporter = ModelProgressRepository(db, job)
    reporter.initialize(models, len(rows), s.inference_document_batch_size)
    model_errors = []
    normalizer = None
    if payload.get("normalize") and not payload.get("repackage_only"):
        from app.services.normalization import NormalizationSession
        from app.services.normalization_catalog import NormalizationCatalog

        terminology = NormalizationCatalog(s)
        method = payload.get("normalization_method", "levenshtein")
        resources = terminology.snapshot(payload["language"], payload["entities"], method=method)
        saved_resources = payload.get("normalization_resources")
        if "normalization_method" not in payload:
            saved_resources = [
                {k: v for k, v in row.items() if k != "models"} for row in saved_resources or []
            ]
        if resources != saved_resources:
            raise ValueError("Terminology configuration changed; resubmit with current resources")
        if "normalization_method" not in payload:
            payload.update(
                normalization_method=method,
                normalization_threshold=0.8,
                normalization_resources=resources,
            )
            with db.connect() as connection:
                connection.execute(
                    "UPDATE jobs SET payload=? WHERE id=? AND content_version=?",
                    (json.dumps(payload), job["id"], job.get("content_version", 0)),
                )
        normalizer = NormalizationSession(
            s,
            root,
            terminology,
            method=method,
            threshold=payload.get("normalization_threshold", 0.8),
        )
        for row in payload.get("normalization_resources", []):
            reporter.ensure(
                f"normalizer-{payload['language']}-{row['entity']}", len(rows), "NORMALIZATION", 0
            )
        normalizer.on_progress = lambda entity, stage, completed, total, unit: reporter.update(
            f"normalizer-{payload['language']}-{entity}", stage, completed, total, unit
        )

    def model_failed(model, exc, stage, count=None):
        reporter.fail(
            model["model_id"],
            exc,
            count if stage in ("INFERENCE", "NORMALIZATION") else None,
        )
        error = {"model_id": model["model_id"], "error_code": type(exc).__name__, "stage": stage}
        if getattr(exc, "reason_code", None):
            error["reason_code"] = exc.reason_code
        if isinstance(exc, ModuleNotFoundError):
            module = (exc.name or "").split(".", 1)[0]
            if module in INFERENCE_MODULES:
                error["missing_module"] = module
        cause = exc
        for _ in range(6):
            response = getattr(cause, "response", None)
            if isinstance(getattr(response, "status_code", None), int):
                error["http_status"] = response.status_code
                break
            cause = getattr(cause, "__cause__", None) or getattr(cause, "__context__", None)
            if cause is None:
                break
        frames = [
            {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
            for frame in traceback.extract_tb(exc.__traceback__)[-20:]
        ]
        logging.getLogger("temu.pipeline").error(
            "model_failed job_id=%s model_id=%s stage=%s error_type=%s reason_code=%s http_status=%s missing_module=%s frames=%s",
            job["id"],
            model["model_id"],
            stage,
            type(exc).__name__,
            error.get("reason_code"),
            error.get("http_status"),
            error.get("missing_module"),
            frames,
        )
        if error not in model_errors:
            model_errors.append(error)
            temp = root / "model-errors.tmp"
            temp.write_text(json.dumps(model_errors, indent=2))
            temp.replace(root / "model-errors.json")
        return {**error, "status": "FAILED"}

    reference, reference_digest = statistics_reference(
        registry.languages[payload["language"]], models
    )
    if "statistics_reference" in payload and (
        reference != payload["statistics_reference"]
        or reference_digest != payload.get("statistics_reference_sha256")
    ):
        raise ValueError("Statistics tokenizer changed since admission")
    if s.model_loading_mode == "on_demand" and adapter is None:
        progress.stage(job["id"], "PREPARING_MODELS")
        cache = ModelCache(s, root)
        prepared = []
        for model in models:
            try:
                reporter.update(model["model_id"], "CHECKING_CACHE")
                cache.on_progress = reporter.callback(model["model_id"])
                prepared.append(cache.prepare(model))
                reporter.update(model["model_id"], "READY", status="WAITING")
            except JobContentChanged:
                raise
            except Exception as exc:
                model_failed(model, exc, "PREPARING_MODELS")
        models = prepared
        if not models:
            progress.mark(
                job["id"], [row["document_id"] for row in rows], "FAILED", "NoModelsPrepared"
            )
            raise ValueError("No configured model could be prepared")
    progress.stage(job["id"], "INFERENCE")
    engine = adapter or (
        HubSession(s.max_loaded_models)
        if s.model_loading_mode == "on_demand"
        else NerLabSession(s.max_loaded_models)
    )
    accumulator = None
    if stats_fn is statistics:
        candidates = (
            [(models[0], reference)]
            if reference
            else [(model, model.get("model_dir")) for model in models]
        )
        for model, candidate in candidates:
            try:
                accumulator = StreamingStatistics(payload["language"], candidate)
                reference = candidate
                reference_digest = (
                    reference_digest
                    or model.get("resolved_revision")
                    or model.get("checkpoint_sha256")
                )
                break
            except JobContentChanged:
                raise
            except Exception as exc:
                model_failed(model, exc, "TOKENIZER")
        if accumulator is None:
            raise ValueError("No selected tokenizer could be loaded")
    started = time.monotonic()
    provenance = []
    normalization_methods = set()
    seen_provenance = set()
    with db.connect() as c:
        limit = c.execute("SELECT reserved_bytes FROM jobs WHERE id=?", (job["id"],)).fetchone()[0]
    pending = []
    for row in rows:
        try:
            with job_lock(s, job["id"]):
                check_content_version(db, job)
                record = read_publication(root, row, snapshot)
                original = (
                    (root / "input" / row["filename"]).read_bytes().decode("utf-8")
                    if record
                    else None
                )
        except (OSError, ValueError, KeyError):
            record = None
        if record:
            reporter.restore_document(record.get("models", []))
            for meta in record.get("models", []):
                if meta.get("status") == "FAILED":
                    error = {k: v for k, v in meta.items() if k != "status"}
                    if error not in model_errors:
                        model_errors.append(error)
                key = json.dumps(meta, sort_keys=True)
                if key not in seen_provenance:
                    provenance.append(meta)
                    seen_provenance.add(key)
            normalization_methods.update(
                span["normalization"].get("method", "bi_encoder")
                for span in record["spans"]
                if span.get("normalization")
            )
        if record and record.get("complete", True):
            progress.publish(
                job["id"],
                row["document_id"],
                len(record["spans"]),
                dict(Counter(r["label"] for r in record["spans"])),
                record["statistics"],
            )
            if accumulator:
                accumulator.add(row["filename"], original, record["spans"])
        elif not payload.get("repackage_only") and (record or row["status"] != "FAILED"):
            if record is not None:
                with job_lock(s, job["id"]):
                    check_content_version(db, job)
                    progress.preview(
                        job["id"],
                        row["document_id"],
                        len(record["spans"]),
                        dict(Counter(span["label"] for span in record["spans"])),
                        record["statistics"],
                    )
            if record is None:
                with job_lock(s, job["id"]):
                    check_content_version(db, job)
                    shutil.rmtree(root / "published" / row["document_id"], ignore_errors=True)
                    with db.connect() as c:
                        c.execute(
                            "UPDATE documents SET status='PENDING',annotation_count=0,entities_by_label='{}',statistics='{}' WHERE job_id=? AND document_id=? AND status!='DELETED'",
                            (job["id"], row["document_id"]),
                        )
                        progress.refresh(c, job["id"])
            pending.append(row)
    shutil.rmtree(root / "building", ignore_errors=True)
    budget = StorageBudget(root, limit, int(s.min_free_disk_mb * 1024**2))

    def finalize(row, raw, record):
        members = (record.get("state") or {}).get("members", {})
        if not any("spans" in outcome for outcome in members.values()):
            progress.mark(job["id"], [row["document_id"]], "FAILED", "NoModelsCompleted")
            return
        text, spans = raw.decode("utf-8"), record["spans"]
        if accumulator:
            per_doc = accumulator.add(row["filename"], text, spans)
            per_doc["tokenizer_reference"] = Path(reference).name
            per_doc["tokenizer_sha256"] = reference_digest
        else:
            _, statistics_rows = stats_fn(
                {row["filename"]: text}, spans, payload["language"], reference
            )
            per_doc = statistics_rows[0]
        metadata = [
            *record["models"],
            *[
                {**error, "status": "FAILED"}
                for error in model_errors
                if error["stage"] == "PREPARING_MODELS"
            ],
        ]
        with job_lock(s, job["id"]):
            check_content_version(db, job)
            count, labels = publish(
                root, row, raw, spans, per_doc, snapshot, metadata, budget=budget
            )
            progress.publish(job["id"], row["document_id"], count, labels, per_doc)
        normalization_methods.update(
            span["normalization"].get("method", "bi_encoder")
            for span in spans
            if span.get("normalization")
        )
        for meta in metadata:
            key = json.dumps(meta, sort_keys=True)
            if key not in seen_provenance:
                provenance.append(meta)
                seen_provenance.add(key)

    try:
        from app.services.phased_processing import DocumentPhases

        phases = DocumentPhases(
            job=job,
            settings=s,
            db=db,
            root=root,
            rows=pending,
            snapshot=snapshot,
            progress=progress,
            reporter=reporter,
            budget=budget,
            engine=engine,
            normalizer=normalizer,
            failed=model_failed,
            finalize=finalize,
        )
        phases.run(models, payload)
        rows = [row for row in progress.rows(job["id"]) if row["status"] != "DELETED"]
        successful = [r for r in rows if r["status"] == "ANNOTATED"]
        if not successful:
            raise ValueError("No documents completed successfully")
        stats = (
            accumulator.result()
            if accumulator
            else {
                "operational": {
                    "documents": len(successful),
                    "annotations": sum(r["annotation_count"] for r in successful),
                    **{
                        key: sum(json.loads(r["statistics"]).get(key, 0) or 0 for r in successful)
                        for key in ("words", "tokens", "sentences")
                    },
                }
            }
        )
        stats["operational"].update(
            seconds=time.monotonic() - started,
            successful_documents=len(successful),
            failed_documents=len(rows) - len(successful),
            failed_models=len({error["model_id"] for error in model_errors}),
            model_errors=model_errors,
            models=provenance,
            normalization=normalizer.metadata if normalizer else [],
        )
        reporter.finish()
        progress.stage(job["id"], "PREPARING_DOWNLOADS")
        manifest = {
            k: payload[k]
            for k in ("language", "entities", "submitter_name", "submitter_email", "documents")
        }
        manifest.update(
            job_id=job["id"],
            created_at=job["created_at"],
            models=provenance,
            partial=len(successful) != len(rows) or bool(model_errors),
            model_errors=model_errors,
            failed_documents=[r["filename"] for r in rows if r["status"] == "FAILED"],
            normalization={
                "requested": bool(payload.get("normalize")),
                "resources": payload.get("normalization_resources", []),
                "indexes": normalizer.metadata if normalizer else [],
                "method": payload.get("normalization_method"),
                "methods_in_results": sorted(normalization_methods),
                "threshold": payload.get("normalization_threshold")
                if payload.get("normalization_method") == "levenshtein"
                else None,
                "score": "Normalized edit similarity"
                if payload.get("normalization_method") == "levenshtein"
                else "Exact normalized text equality"
                if payload.get("normalization_method") == "exact"
                else "Cosine similarity, not a calibrated probability",
                "english_fallback": "Original mention queried against English terminology; no automatic translation",
            },
            ner_lab_commit="8640d4797b081a5f6b66d9b45c11269542a79a26",
            offsets="Unicode code points [start,end)",
            filename_convention="original relative path including .txt",
            evaluation="Not computed: no gold standard",
        )
        with job_lock(s, job["id"]):
            check_content_version(db, job)
            timing = package_publications(root, rows, payload, stats, manifest, budget=budget)
        stats["operational"].update(timing)
        return stats["operational"]
    finally:
        if normalizer:
            normalizer.close()
        if hasattr(engine, "close"):
            engine.close()
