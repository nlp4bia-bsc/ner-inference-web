"""Job admission, status and private result access, independent of HTTP routing."""

import json
import secrets
import shutil
import time
import uuid
from datetime import datetime, timezone

from app.errors import ServiceError
from app.permissions.policies import document_limit, require_owner, user
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
        account = user()
        if self.settings.require_email_verification and not account["email_verified_at"]:
            raise ServiceError("verification_required", 403)
        form = form.model_copy(
            update={"submitter_name": account["full_name"], "submitter_email": account["email"]}
        )
        limit = document_limit(account["access_tier"], self.settings.max_documents_per_job)
        ingestion_settings = self.settings.model_copy(update={"max_documents_per_job": limit})
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
                streams, staging / "input", ingestion_settings, source_type, on_bytes=grow
            )
            payload = {
                **form.model_dump(),
                "documents": [r["original_relative_path"] for r in references],
                "document_references": references,
                "statistics_reference": reference,
                "statistics_reference_sha256": reference_digest,
                "catalog_version": 3,
                "entities": sorted(
                    {label for m in selected for label in m["label_mapping"].values()}
                ),
                "selected_models": model_snapshot(selected),
            }
            if form.normalize:
                from app.services.normalization_catalog import NormalizationCatalog

                payload["normalization_resources"] = NormalizationCatalog(self.settings).snapshot(
                    form.language, payload["entities"], method=form.normalization_method
                )
            staging.rename(self.storage.job(job_id))
            self.db.accept(
                job_id,
                token,
                payload,
                len(references),
                ip,
                lease=lease,
                owner_user_id=account["id"],
                access_tier=account["access_tier"],
                owner_session_hash=account["session_hash"],
            )
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            self.storage.delete(job_id)
            raise
        import logging

        from app.services.worker_status import worker_status

        logging.getLogger("temu.queue").info(
            "job_queued job_id=%s documents=%s models=%s worker_state=%s",
            job_id,
            len(references),
            len(selected),
            worker_status(self.db)["state"],
        )
        return {
            "job_id": job_id,
            "status": "QUEUED",
            "token": token,
            "url": self.settings.public_base_url.rstrip("/") + "/jobs/" + job_id,
        }

    def available(self, token: str) -> dict:
        job = require_owner(self.db.get(token))
        if job["status"] == "DELETED":
            raise ServiceError("Results have been deleted or are scheduled for deletion.", 410)
        if job["status"] == "EXPIRED" or (job["expires_at"] and job["expires_at"] <= time.time()):
            raise ServiceError("Results have expired and downloads are no longer available.", 410)
        return job

    def quota(self):
        from app.services.document_management import quota

        return quota(self.db, user())

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
                    "SELECT count(*) FROM jobs WHERE status='QUEUED' AND seq<=? AND owner_user_id=?",
                    (job["seq"], user()["id"]),
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

    def history(self, offset=0):
        account = user()
        with self.db.connect() as c:
            rows = c.execute(
                """SELECT id,CASE WHEN status='DELETED' THEN 'DELETED' WHEN expires_at<=? THEN 'EXPIRED' ELSE status END AS status,
                document_count,processed_documents,created_at,completed_at,expires_at,
                json_extract(payload,'$.language') AS language,
                json_extract(payload,'$.documents[0]') AS name,
                json_extract(payload,'$.selected_models') AS selected_models
                FROM jobs WHERE owner_user_id=? AND status!='DELETED' ORDER BY seq DESC LIMIT 100 OFFSET ?""",
                (time.time(), account["id"], offset),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["models"] = [
                m["model_id"] for m in json.loads(item.pop("selected_models") or "[]")
            ]
            item["name"] = item["name"] or item["id"][:8]
            result.append(item)
        return result

    def workspace_metrics(self):
        """Aggregate only this owner's retained jobs, independently of history pagination."""
        with self.db.connect() as c:
            row = c.execute(
                """SELECT COALESCE(sum(status IN ('QUEUED','PROCESSING')),0) AS active,
                COALESCE(sum(status IN ('COMPLETED','COMPLETED_WITH_ERRORS')),0) AS completed,
                COALESCE(sum(processed_documents>0 AND status!='EXPIRED'
                  AND (expires_at IS NULL OR expires_at>?)),0) AS available
                FROM jobs WHERE owner_user_id=?""",
                (time.time(), user()["id"]),
            ).fetchone()
        return dict(row)
