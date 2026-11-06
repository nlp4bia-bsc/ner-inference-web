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
from app.persistence.progress import ProgressRepository
from app.services.hub_inference import HubSession
from app.services.incremental_export import package_publications
from app.services.inference import NerLabSession, merge_predictions
from app.services.model_cache import ModelCache
from app.services.publication import publish, read_publication
from app.services.registry import Registry, model_snapshot, statistics_reference
from app.services.runtime import INFERENCE_MODULES
from app.services.statistics import StreamingStatistics, statistics
from app.storage import LocalStorage, StorageBudget, directory_bytes


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
    rows = progress.rows(job["id"])
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
        rows = progress.rows(job["id"])
    model_errors = []

    def model_failed(model, exc, stage):
        error = {"model_id": model["model_id"], "error_code": type(exc).__name__, "stage": stage}
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
            "model_failed job_id=%s model_id=%s stage=%s error_type=%s http_status=%s missing_module=%s frames=%s",
            job["id"],
            model["model_id"],
            stage,
            type(exc).__name__,
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
                prepared.append(cache.prepare(model))
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
            except Exception as exc:
                model_failed(model, exc, "TOKENIZER")
        if accumulator is None:
            raise ValueError("No selected tokenizer could be loaded")
    started = time.monotonic()
    provenance = []
    seen_provenance = set()
    with db.connect() as c:
        limit = c.execute("SELECT reserved_bytes FROM jobs WHERE id=?", (job["id"],)).fetchone()[0]
    pending = []
    for row in rows:
        try:
            record = read_publication(root, row, snapshot)
        except (OSError, ValueError, KeyError):
            record = None
        if record:
            for meta in record.get("models", []):
                if meta.get("status") == "FAILED":
                    error = {k: v for k, v in meta.items() if k != "status"}
                    if error not in model_errors:
                        model_errors.append(error)
                key = json.dumps(meta, sort_keys=True)
                if key not in seen_provenance:
                    provenance.append(meta)
                    seen_provenance.add(key)
            progress.publish(
                job["id"],
                row["document_id"],
                len(record["spans"]),
                dict(Counter(r["label"] for r in record["spans"])),
                record["statistics"],
            )
            if accumulator:
                accumulator.add(
                    row["filename"],
                    (root / "input" / row["filename"]).read_bytes().decode("utf-8"),
                    record["spans"],
                )
        elif row["status"] != "FAILED":
            shutil.rmtree(
                root / "published" / (row["document_id"] + ".building"), ignore_errors=True
            )
            shutil.rmtree(root / "published" / row["document_id"], ignore_errors=True)
            if row["status"] != "PENDING":
                with db.connect() as c:
                    c.execute(
                        "UPDATE documents SET status='PENDING' WHERE job_id=? AND document_id=?",
                        (job["id"], row["document_id"]),
                    )
                    progress.refresh(c, job["id"])
            pending.append(row)
    shutil.rmtree(root / "building", ignore_errors=True)
    budget = StorageBudget(root, limit, int(s.min_free_disk_mb * 1024**2))
    try:
        for offset in range(0, len(pending), s.inference_document_batch_size):
            batch = pending[offset : offset + s.inference_document_batch_size]
            identities = [r["document_id"] for r in batch]
            progress.mark(job["id"], identities, "PROCESSING")
            raw = {r["filename"]: (root / "input" / r["filename"]).read_bytes() for r in batch}
            texts = {name: data.decode("utf-8") for name, data in raw.items()}
            try:
                predictions = []
                metadata = [
                    {**error, "status": "FAILED"}
                    for error in model_errors
                    if error["stage"] == "PREPARING_MODELS"
                ]
                ordered = (
                    models
                    if any(m.get("requires") for m in models)
                    or (offset // s.inference_document_batch_size) % 2 == 0
                    else list(reversed(models))
                )
                for i, model in enumerate(ordered):
                    try:
                        if model.get("task", "ner") != "ner" or model.get("requires"):
                            # Never feed an annotation-dependent classifier raw text alone.
                            if not hasattr(engine, "classify"):
                                raise ValueError("No adapter for the selected dependent task")
                            upstream = {m["model_id"]: spans for m, spans in predictions}
                            inputs = {key: upstream[key] for key in model["requires"]}
                            spans, meta = engine.classify(model, texts, inputs, s.device)
                        else:
                            spans, meta = engine.predict(
                                model, texts, root / "building" / f"model-{i}", s.device
                            )
                        resolved = {
                            **model,
                            "label_mapping": meta.get("label_mapping", model["label_mapping"]),
                        }
                        merge_predictions(
                            texts, [(resolved, spans)]
                        )  # Reject only this model's malformed output.
                        predictions.append((resolved, spans))
                        metadata.append(meta)
                    except Exception as exc:
                        metadata.append(model_failed(model, exc, "INFERENCE"))
                if not predictions:
                    raise ValueError("No model completed this batch")
                merged = merge_predictions(texts, predictions)
            except Exception as exc:
                logging.getLogger("temu.pipeline").error(
                    "microbatch_failed job_id=%s error_type=%s", job["id"], type(exc).__name__
                )
                progress.mark(job["id"], identities, "FAILED", type(exc).__name__)
                continue
            grouped = {r["filename"]: [] for r in batch}
            for span in merged:
                grouped[span["filename"]].append(span)
            if accumulator:
                per_doc = [
                    accumulator.add(r["filename"], texts[r["filename"]], grouped[r["filename"]])
                    for r in batch
                ]
            else:
                _, per_doc = stats_fn(texts, merged, payload["language"], reference)
            if accumulator:
                for record in per_doc:
                    record["tokenizer_reference"] = Path(reference).name
                    record["tokenizer_sha256"] = reference_digest
            stats_by_name = {r["filename"]: r for r in per_doc}
            for row in batch:
                count, labels = publish(
                    root,
                    row,
                    raw[row["filename"]],
                    grouped[row["filename"]],
                    stats_by_name[row["filename"]],
                    snapshot,
                    metadata,
                    budget=budget,
                )
                progress.publish(
                    job["id"], row["document_id"], count, labels, stats_by_name[row["filename"]]
                )
            provenance.extend(metadata)
            shutil.rmtree(root / "building", ignore_errors=True)
            used = directory_bytes(root)
            with db.connect() as c:
                c.execute("UPDATE jobs SET storage_bytes=? WHERE id=?", (used, job["id"]))
                cap = c.execute(
                    "SELECT reserved_bytes FROM jobs WHERE id=?", (job["id"],)
                ).fetchone()[0]
            if used > cap:
                raise RuntimeError("Job exceeded its storage reservation")
        rows = progress.rows(job["id"])
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
        )
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
            ner_lab_commit="8640d4797b081a5f6b66d9b45c11269542a79a26",
            offsets="Unicode code points [start,end)",
            filename_convention="original relative path including .txt",
            evaluation="Not computed: no gold standard",
        )
        timing = package_publications(root, rows, payload, stats, manifest, budget=budget)
        stats["operational"].update(timing)
        return stats["operational"]
    finally:
        if hasattr(engine, "close"):
            engine.close()
