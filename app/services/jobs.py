"""Job admission, status and private result access, independent of HTTP routing."""

import json
import secrets
import shutil
import time
import uuid
from datetime import datetime, timezone

from app.errors import ServiceError
from app.services.documents import load_documents


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


class JobService:
    def __init__(self, settings, database, storage, registry):
        self.settings, self.db, self.storage, self.registry = settings, database, storage, registry

    def submit(self, form, uploaded: list[tuple[str, bytes]], ip: str):
        selected = self.registry.select(form.language, form.entities)
        documents = load_documents(uploaded, self.settings)
        job_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        staging = self.storage.root / "staging" / job_id
        staging.mkdir()
        try:
            for name, data in documents.items():
                path = staging / "input" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            payload = {
                **form.model_dump(),
                "documents": list(documents),
                "selected_models": [
                    {
                        k: m.get(k)
                        for k in (
                            "model_id",
                            "version",
                            "model_dir",
                            "checkpoint_sha256",
                            "min_score",
                            "batch_size",
                        )
                    }
                    for m in selected
                ],
            }
            staging.rename(self.storage.job(job_id))
            self.db.accept(job_id, token, payload, len(documents), ip)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            self.storage.delete(job_id)
            raise
        return {
            "job_id": job_id,
            "status": "QUEUED",
            "token": token,
            "url": self.settings.public_base_url.rstrip("/") + "/jobs/" + token,
        }

    def available(self, token: str) -> dict:
        job = self.db.get(token)
        if job["status"] == "EXPIRED" or (job["expires_at"] and job["expires_at"] <= time.time()):
            raise ServiceError("Results have expired and downloads are no longer available.", 410)
        return job

    def completed(self, token: str) -> dict:
        job = self.available(token)
        if job["status"] != "COMPLETED":
            raise ServiceError("Results are not ready.", 409)
        return job

    def result_path(self, token: str, name: str):
        job = self.completed(token)
        path = self.storage.job(job["id"]) / "output" / name
        if not path.is_file():
            raise ServiceError("Result temporarily unavailable.", 503)
        return path

    def status(self, token: str) -> dict:
        job = self.available(token)
        payload = json.loads(job["payload"])
        with self.db.connect() as c:
            position = (
                c.execute(
                    "SELECT count(*) FROM jobs WHERE status='QUEUED' AND seq<=?", (job["seq"],)
                ).fetchone()[0]
                if job["status"] == "QUEUED"
                else None
            )
        return {
            **{
                k: job[k]
                for k in ("status", "document_count", "processed_documents", "error_summary")
            },
            "job_id": job["id"],
            "queue_position": position,
            "language": payload["language"],
            "entities": payload["entities"],
            **{k: iso(job[k]) for k in ("created_at", "started_at", "completed_at", "expires_at")},
            "summary": json.loads(job["summary"]) if job["summary"] else None,
            "downloads_available": job["status"] == "COMPLETED",
        }
