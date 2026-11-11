"""Lazy administrator navigation over existing project/document publications."""

import json
import logging
import time

from app.admin.statistics import (
    TEXT_METRICS,
    aggregate_statistics,
    empty_statistics,
    saved_statistics,
    text_statistics,
)
from app.auth.sessions import require_live
from app.errors import ServiceError
from app.permissions.policies import require_admin
from app.persistence.job_locks import job_lock
from app.visualization.repository import DocumentRepository

UNASSIGNED = "unassigned"


class AdminExplorer:
    def __init__(self, jobs):
        self.jobs = jobs
        self.db = jobs.db
        self.repository = DocumentRepository(jobs)

    def authorize(self, connection):
        return require_live(connection, require_admin(), self.jobs.settings, admin=True)

    @staticmethod
    def project_metadata(job):
        payload = json.loads(job["payload"])
        models = payload.get("selected_models", [])
        return {
            "id": job["id"],
            "name": payload.get("job_name") or next(iter(payload.get("documents", [])), job["id"]),
            "language": payload.get("language"),
            "status": job["status"],
            "stage": job["stage"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "content_version": job["content_version"],
            "expires_at": job["expires_at"],
            "configured_models": [
                m.get("id", m.get("model_id")) if isinstance(m, dict) else m for m in models
            ],
            "available": job["status"] not in ("DELETED", "EXPIRED")
            and (job["expires_at"] is None or job["expires_at"] > time.time()),
        }

    def users(self, offset=0, limit=25):
        with self.db.connect() as connection:
            self.authorize(connection)
            total = connection.execute("SELECT count(*) FROM users").fetchone()[0]
            orphaned = bool(
                connection.execute(
                    "SELECT 1 FROM jobs WHERE owner_user_id IS NULL AND status!='DELETED' LIMIT 1"
                ).fetchone()
            )
            rows = connection.execute(
                "SELECT id,full_name,email,institution,approval_status,account_status FROM users ORDER BY created_at,id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            counts = dict(
                connection.execute(
                    "SELECT owner_user_id,count(*) FROM jobs WHERE status!='DELETED' GROUP BY owner_user_id"
                ).fetchall()
            )
        items = [{**dict(row), "project_count": counts.get(row["id"], 0)} for row in rows]
        if orphaned and offset <= total < offset + limit:
            items.append(
                {
                    "id": UNASSIGNED,
                    "full_name": "Unassigned owner",
                    "email": "",
                    "institution": "",
                    "project_count": counts.get(None, 0),
                }
            )
        return {"items": items, "total": total + orphaned, "offset": offset, "limit": limit}

    def _projects(self, owner):
        with self.db.connect() as connection:
            self.authorize(connection)
            if owner is ...:
                rows = connection.execute(
                    "SELECT * FROM jobs WHERE status!='DELETED' ORDER BY seq DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM jobs WHERE owner_user_id IS ? AND status!='DELETED' ORDER BY seq DESC",
                    (owner,),
                ).fetchall()
        return [dict(row) for row in rows]

    def overview(self, owner=...):
        snapshots = {}
        for job in self._projects(owner):
            try:
                snapshots[job["id"]] = self.project(job["id"])
            except ServiceError as exc:
                if exc.status not in (404, 410):
                    raise
        summaries = []
        # Erasure can commit between reading different projects. Recheck the live
        # set and generation before combining so deleted content is not restored
        # by a previously cached project summary.
        for job in self._projects(owner):
            if not self.project_metadata(job)["available"]:
                summaries.append({"expired_projects": 1})
                continue
            snapshot = snapshots.get(job["id"])
            if snapshot is None or snapshot["project"]["content_version"] != job["content_version"]:
                try:
                    snapshot = self.project(job["id"])
                except ServiceError as exc:
                    if exc.status not in (404, 410):
                        raise
                    continue
            summaries.append(snapshot["statistics"])
        result = aggregate_statistics(summaries)
        with self.db.connect() as connection:
            self.authorize(connection)
            result["users"] = (
                connection.execute("SELECT count(*) FROM users").fetchone()[0]
                if owner is ...
                else int(owner is not None)
            )
        return {"statistics": result, "updated_at": time.time()}

    def projects(self, identity, offset=0, limit=25):
        with self.db.connect() as connection:
            self.authorize(connection)
            row = connection.execute(
                "SELECT id,full_name,email,institution FROM users WHERE id=?", (identity,)
            ).fetchone()
        if not row and identity != UNASSIGNED:
            raise ServiceError("Not found", 404)
        owner = None if identity == UNASSIGNED else identity
        rows = self._projects(owner)
        return {
            "user": dict(row)
            if row
            else {
                "id": UNASSIGNED,
                "full_name": "Unassigned owner",
                "email": "",
                "institution": "",
            },
            "items": [self.project_metadata(row) for row in rows[offset : offset + limit]],
            "total": len(rows),
            "offset": offset,
            "limit": limit,
            **self.overview(owner),
        }

    def _document(self, root, row, language):
        path = root / "published" / row["document_id"] / "artifact.json"
        if not path.is_file():
            path = root / "viewer" / (row["document_id"] + ".json")
        available = (root / "input" / row["filename"]).is_file()
        stats = empty_statistics()
        stats["documents"] = 1
        stats["document_states"] = {row["status"]: 1}
        if available and path.is_file():
            try:
                stat = path.stat()
                stats.update(saved_statistics(path, stat.st_mtime_ns, stat.st_size, stat.st_ino))
                stats["documents"] = 1
                stats["document_states"] = {row["status"]: 1}
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logging.getLogger("temu.admin").warning(
                    "statistics_unavailable document_id=%s error_type=%s",
                    row["document_id"],
                    type(exc).__name__,
                )
                available = False
        elif row["annotation_count"]:
            available = False
        stats["unavailable_documents"] = int(not available)
        stats["documents_with_annotations"] = int(stats["annotations"] > 0)
        stats["documents_by_language"] = {language: 1}
        stats["annotations_by_language"] = {language: stats["annotations"]}
        stats["text_statistics"] = (
            text_statistics(row.get("statistics", {})) if available else dict.fromkeys(TEXT_METRICS)
        )
        return {
            "document_id": row["document_id"],
            "filename": row["filename"],
            "status": row["status"],
            "updated_at": row.get("updated_at"),
            "original_available": (root / "input" / row["filename"]).is_file(),
            "statistics_available": available,
            "statistics": stats,
        }

    def project(self, identity, offset=0, limit=25):
        job = self.jobs.available(identity)
        with job_lock(self.jobs.settings, job["id"]):
            with self.db.connect() as connection:
                self.authorize(connection)
            job = self.jobs.available(identity)
            root = self.jobs.storage.job(job["id"])
            documents = [
                self._document(root, row, json.loads(job["payload"]).get("language") or "oth")
                for row in self.repository.index(job["id"])
            ]
            statistics = aggregate_statistics(row["statistics"] for row in documents)
            statistics["projects"] = 1
            statistics["job_states"] = {job["status"]: 1}
            statistics["partial_projects"] = int(
                job["status"] != "COMPLETED" or statistics["unavailable_documents"] > 0
            )
            with self.db.connect() as connection:
                models = connection.execute(
                    "SELECT model_id,kind,status,completed_documents,total_documents FROM model_progress WHERE job_id=? AND content_version=? ORDER BY model_id",
                    (job["id"], job["content_version"]),
                ).fetchall()
            return {
                "project": self.project_metadata(job),
                "items": documents[offset : offset + limit],
                "total": len(documents),
                "offset": offset,
                "limit": limit,
                "statistics": statistics,
                "model_execution": [dict(row) for row in models],
                "updated_at": time.time(),
            }
