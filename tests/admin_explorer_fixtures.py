"""Known synthetic overlapping, normalized publications; no real patient data."""

import json
import shutil

from app.persistence.job_locks import job_lock
from app.persistence.progress import ProgressRepository
from app.services.export import package
from app.services.publication import publish


def publish_known_results(app, accepted, *, complete=True, normalized=True):
    database, jobs = app.state.db, app.state.jobs
    job = database.get(accepted["job_id"])
    payload = json.loads(job["payload"])
    root = jobs.storage.job(job["id"])
    progress = ProgressRepository(database)
    documents, spans, native = {}, [], []
    with job_lock(app.state.settings, job["id"]):
        with database.connect() as connection:
            connection.execute(
                "UPDATE jobs SET status='PROCESSING',stage='INFERENCE',processing_version=content_version WHERE id=?",
                (job["id"],),
            )
        for index, row in enumerate(progress.rows(job["id"])):
            raw = (root / "input" / row["filename"]).read_bytes()
            documents[row["filename"]] = raw
            text = raw.decode()
            entries = [
                {
                    "label": "DISEASE",
                    "start_span": 0,
                    "end_span": 2,
                    "text": text[:2],
                    "model_id": "A",
                    "model_ids": ["A", "B"],
                },
                {
                    "label": "SYMPTOM",
                    "start_span": 1,
                    "end_span": 3,
                    "text": text[1:3],
                    "model_id": "B",
                    "model_ids": ["B"],
                },
                {
                    "label": "MEDICATION",
                    "start_span": 0,
                    "end_span": 1,
                    "text": text[:1],
                    "model_id": "C",
                    "model_ids": ["C"],
                },
            ]
            if normalized:
                entries[2]["normalization"] = {
                    "method": "levenshtein",
                    "threshold": 0.8,
                    "score_kind": "normalized_similarity",
                    "references": [{"code_system": "UMLS", "code": "C123"}],
                    "code": "C123",
                    "code_system": "UMLS",
                    "term": "Synthetic concept",
                    "score": 1.0,
                    "candidates": [],
                    "language": "en",
                    "requested_language": "es",
                    "fallback_to_english": True,
                    "model": None,
                    "model_revision": None,
                    "gazetteer_sha256": "synthetic",
                    "index": "synthetic",
                    "max_length": None,
                }
            for entry in entries:
                entry.update(filename=row["filename"], score=0.9)
            stats = {
                "filename": row["filename"],
                "characters": len(text),
                "words": 2,
                "tokens": 3,
                "sentences": 1,
                "entities_total": 3,
                "processing_status": "COMPLETED",
            }
            count, labels = publish(
                root,
                row,
                raw,
                entries,
                stats,
                payload["selected_models"],
                [{"model_id": name} for name in ["A", "B", "C"]],
                complete=complete,
            )
            if not complete:
                progress.preview(job["id"], row["document_id"], count, labels, stats)
                break
            progress.publish(job["id"], row["document_id"], count, labels, stats)
            spans.extend(entries)
            native.append(stats)
        if complete:
            shutil.rmtree(root / "output", ignore_errors=True)
            summary = {
                "documents": len(documents),
                "annotations": len(spans),
                "characters": sum(map(len, documents.values())),
                "words": 2 * len(documents),
                "tokens": 3 * len(documents),
                "sentences": len(documents),
            }
            package(
                root / "output",
                documents,
                spans,
                {**payload, "entities": ["DISEASE", "SYMPTOM", "MEDICATION"]},
                {"operational": summary},
                native,
                {"source": "synthetic admin fixture"},
            )
            database.finish(job["id"], summary)
    return progress.rows(job["id"])
