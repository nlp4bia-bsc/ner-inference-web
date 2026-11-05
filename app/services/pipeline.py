"""Bounded microbatches, persistent publication, restart reuse and final streaming exports."""

import json
import logging
import shutil
import time
from collections import Counter

from app.config import Settings
from app.db import Database
from app.persistence.progress import ProgressRepository
from app.services.incremental_export import package_publications
from app.services.inference import NerLabSession, merge_predictions
from app.services.publication import publish, read_publication
from app.services.registry import Registry, model_snapshot, statistics_reference
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
    progress.stage(job["id"], "INFERENCE")
    engine = adapter or NerLabSession(s.max_loaded_models)
    reference, reference_digest = statistics_reference(
        registry.languages[payload["language"]], models
    )
    if "statistics_reference" in payload and (
        reference != payload["statistics_reference"]
        or reference_digest != payload.get("statistics_reference_sha256")
    ):
        raise ValueError("Statistics tokenizer changed since admission")
    accumulator = (
        StreamingStatistics(payload["language"], reference) if stats_fn is statistics else None
    )
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
                metadata = []
                ordered = (
                    models
                    if any(m.get("requires") for m in models)
                    or (offset // s.inference_document_batch_size) % 2 == 0
                    else list(reversed(models))
                )
                for i, model in enumerate(ordered):
                    if model.get("task", "ner") != "ner" or model.get("requires"):
                        # Never feed an annotation-dependent classifier raw text alone.
                        if not hasattr(engine, "classify"):
                            raise ValueError("No audited adapter for the selected dependent task")
                        upstream = {m["model_id"]: spans for m, spans in predictions}
                        inputs = {key: upstream[key] for key in model["requires"]}
                        spans, meta = engine.classify(model, texts, inputs, s.device)
                    else:
                        spans, meta = engine.predict(
                            model, texts, root / "building" / f"model-{i}", s.device
                        )
                    predictions.append((model, spans))
                    metadata.append(meta)
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
                from pathlib import Path

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
            partial=len(successful) != len(rows),
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
