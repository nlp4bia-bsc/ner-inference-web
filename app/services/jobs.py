"""Job admission, status and private result access, independent of HTTP routing."""

import json
import secrets
import shutil
import time
import uuid
from datetime import datetime, timezone

from app.errors import ServiceError
from app.persistence.progress import ProgressRepository
from app.services.documents import ingest
from app.services.registry import model_snapshot, statistics_reference


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


class JobService:
    def __init__(self, settings, database, storage, registry):
        self.settings, self.db, self.storage, self.registry = settings, database, storage, registry

    def submit(self, form, uploaded: list[tuple[str, bytes]], ip: str):
        import io

        return self.submit_streams(form, [(name, io.BytesIO(data)) for name, data in uploaded], ip)

    def submit_streams(self, form, streams, ip, source_type="TXT_UPLOAD", lease=None):
        selected = self.registry.select(form.language, form.entities, form.models)
        reference, reference_digest = statistics_reference(
            self.registry.languages[form.language], selected
        )
        job_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        staging = self.storage.root / "staging" / job_id
        staging.mkdir()
        if lease:
            self.db.touch_upload(lease, job_id)
        last_touch = time.monotonic()
        reserved = 2 * self.settings.upload_bytes + int(
            self.settings.storage_reserve_extra_mb * 1024**2
        )

        def grow(total):
            nonlocal reserved, last_touch
            if lease and time.monotonic() - last_touch > 5:
                self.db.touch_upload(lease)
                last_touch = time.monotonic()
            target = self.db.reservation(total)
            if lease and target > reserved:
                self.db.resize_upload(lease, target)
                reserved = target

        try:
            references = ingest(
                streams, staging / "input", self.settings, source_type, on_bytes=grow
            )
            payload = {
                **form.model_dump(),
                "documents": [r["original_relative_path"] for r in references],
                "document_references": references,
                "statistics_reference": reference,
                "statistics_reference_sha256": reference_digest,
                "catalog_version": 2,
                "entities": sorted(
                    {label for m in selected for label in m["label_mapping"].values()}
                ),
                "selected_models": model_snapshot(selected),
            }
            staging.rename(self.storage.job(job_id))
            self.db.accept(job_id, token, payload, len(references), ip, lease=lease)
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
        if job["status"] not in ("COMPLETED", "COMPLETED_WITH_ERRORS"):
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
            "models": [m["model_id"] for m in payload["selected_models"]],
            **{k: iso(job[k]) for k in ("created_at", "started_at", "completed_at", "expires_at")},
            "summary": json.loads(job["summary"]) if job["summary"] else None,
            "downloads_available": job["status"] in ("COMPLETED", "COMPLETED_WITH_ERRORS"),
            "progress": ProgressRepository(self.db).snapshot(job),
            "server_now": iso(time.time()),
        }
