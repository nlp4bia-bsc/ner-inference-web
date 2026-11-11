"""Promote existing legacy exports before erasure, preserving every remaining span."""

import json
import time

from app.services.publication import publish
from app.visualization.repository import DocumentRepository


def prepare_legacy_documents(service, job, connection):
    """Caller holds the job lock/write transaction; originals/exports stay intact on failure."""
    repository = DocumentRepository(service)
    records = repository.index(job["id"])
    root = service.storage.job(job["id"])
    payload = json.loads(job["payload"])
    historical = connection.execute(
        "SELECT id,document_id,filename FROM upload_ledger WHERE job_id=? ORDER BY id",
        (job["id"],),
    ).fetchall()
    assigned = set()
    for row in records:
        annotations = repository.annotations(job["id"], row["document_id"])
        spans = [
            {
                **{
                    key: value
                    for key, value in annotation.items()
                    if key not in ("id", "document_id", "start", "end")
                },
                "filename": row["filename"],
                "start_span": annotation["start"],
                "end_span": annotation["end"],
            }
            for annotation in annotations
        ]
        raw = (root / "input" / row["filename"]).read_bytes()
        models = sorted(
            {
                model
                for annotation in annotations
                for model in [*(annotation.get("model_ids") or []), annotation.get("model_id")]
                if model
            }
        )
        count, labels = publish(
            root,
            row,
            raw,
            spans,
            row.get("statistics", {}),
            payload.get("selected_models", []),
            [{"model_id": model} for model in models],
        )
        connection.execute(
            """INSERT INTO documents(job_id,document_id,filename,source_type,size_bytes,status,annotation_count,entities_by_label,statistics,updated_at)
            VALUES(?,?,?,'TXT_UPLOAD',?,'ANNOTATED',?,?,?,?)""",
            (
                job["id"],
                row["document_id"],
                row["filename"],
                len(raw),
                count,
                json.dumps(labels),
                json.dumps(row.get("statistics", {})),
                time.time(),
            ),
        )
        if job["owner_user_id"] is None:
            continue
        previous = next(
            (
                r
                for r in historical
                if r["id"] not in assigned
                and (r["document_id"] == row["document_id"] or r["filename"] == row["filename"])
            ),
            None,
        )
        if previous is None:
            previous = next(
                (
                    r
                    for r in historical
                    if r["id"] not in assigned and r["filename"] == "Historical document"
                ),
                None,
            )
        if previous:
            assigned.add(previous["id"])
            connection.execute(
                "UPDATE upload_ledger SET document_id=?,filename=?,size_bytes=? WHERE id=?",
                (row["document_id"], row["filename"], len(raw), previous["id"]),
            )
        else:
            connection.execute(
                "INSERT OR IGNORE INTO upload_ledger(owner_user_id,job_id,document_id,filename,language,size_bytes,uploaded_at) VALUES(?,?,?,?,?,?,?)",
                (
                    job["owner_user_id"],
                    job["id"],
                    row["document_id"],
                    row["filename"],
                    payload["language"],
                    len(raw),
                    job["created_at"],
                ),
            )
