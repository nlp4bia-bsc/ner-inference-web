"""Idempotent document publication and persistent progress, independent of HTTP."""

import json
import time
from collections import Counter


class ProgressRepository:
    def __init__(self, database):
        self.db = database

    def rows(self, job_id):
        with self.db.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM documents WHERE job_id=? ORDER BY filename", (job_id,)
                )
            ]

    def stage(self, job_id, stage):
        with self.db.connect() as c:
            c.execute(
                "UPDATE jobs SET stage=?,updated_at=? WHERE id=?", (stage, time.time(), job_id)
            )

    def mark(self, job_id, ids, status, error=None):
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            for identity in ids:
                c.execute(
                    "UPDATE documents SET status=?,error_code=?,updated_at=? WHERE job_id=? AND document_id=? AND status NOT IN ('ANNOTATED','DELETED')",
                    (status, error, time.time(), job_id, identity),
                )
            self.refresh(c, job_id)

    def publish(self, job_id, identity, count, labels, stats):
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                "UPDATE documents SET status='ANNOTATED',annotation_count=?,entities_by_label=?,statistics=?,updated_at=?,error_code=NULL WHERE job_id=? AND document_id=? AND status!='DELETED'",
                (count, json.dumps(labels), json.dumps(stats), time.time(), job_id, identity),
            )
            self.refresh(c, job_id)

    @staticmethod
    def refresh(c, job_id):
        c.execute(
            "UPDATE jobs SET processed_documents=(SELECT count(*) FROM documents WHERE job_id=? AND status='ANNOTATED'),updated_at=? WHERE id=?",
            (job_id, time.time(), job_id),
        )

    def snapshot(self, job):
        rows = self.rows(job["id"])
        counts = Counter(r["status"] for r in rows)
        total = max(0, job["document_count"] - counts["DELETED"])
        annotated = counts["ANNOTATED"] if rows else job["processed_documents"]
        published = [json.loads(r["statistics"]) for r in rows if r["status"] == "ANNOTATED"]
        provisional = {
            key: sum(r[key] for r in published if r.get(key) is not None)
            if any(r.get(key) is not None for r in published)
            else None
            for key in ("words", "tokens", "sentences")
        }
        if not rows and job.get("summary"):
            saved = json.loads(job["summary"])
            provisional = {key: saved.get(key) for key in ("words", "tokens", "sentences")}
        else:
            saved = {}
        return {
            "provisional_statistics": provisional,
            "mentions": sum(r["annotation_count"] for r in rows if r["status"] == "ANNOTATED")
            if rows
            else saved.get("annotations", 0),
            "partial_results": annotated > 0 and job["status"] != "COMPLETED",
            "status": job["status"],
            "stage": job.get("stage") or job["status"],
            "total_documents": total,
            "annotated_documents": annotated,
            "processing_documents": counts["PROCESSING"],
            "pending_documents": counts["PENDING"] if rows else total - annotated,
            "failed_documents": counts["FAILED"],
            "deleted_documents": counts["DELETED"],
            "progress_percent": annotated / total * 100 if total else 0,
            "updated_at": job.get("updated_at") or job["created_at"],
        }
