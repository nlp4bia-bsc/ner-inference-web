"""Persistent per-model progress with generation guards and no clinical content."""

import json
import logging
import math
import time
from datetime import datetime, timezone

from app.persistence.job_locks import check_content_version

log = logging.getLogger("temu.progress")


class ModelProgressRepository:
    def __init__(self, database, job):
        self.db, self.job = database, job
        self.logs = {}

    def initialize(self, models, total, batch_size, resumed=0):
        for model in models:
            self.ensure(model["model_id"], total, "NER", resumed, math.ceil(total / batch_size))

    def ensure(self, model_id, total, kind="NER", resumed=0, batch_count=0):
        check_content_version(self.db, self.job)
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            check_content_version(self.db, self.job)
            connection.execute(
                """INSERT INTO model_progress(job_id,model_id,kind,content_version,total_documents,
                   completed_documents,batch_count,updated_at) VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(job_id,model_id) DO UPDATE SET kind=excluded.kind,
                   content_version=excluded.content_version,total_documents=excluded.total_documents,
                   completed_documents=excluded.completed_documents,failed_documents=0,
                   batch_count=excluded.batch_count,status='PENDING',stage='PENDING',
                   completed_units=0,total_units=NULL,unit=NULL,error_code=NULL,
                   batch_index=0,batch_documents=0,started_at=NULL,updated_at=excluded.updated_at""",
                (
                    self.job["id"],
                    model_id,
                    kind,
                    self.job.get("content_version", 0),
                    total,
                    resumed,
                    batch_count,
                    time.time(),
                ),
            )

    def update(self, model_id, stage, completed=0, total=None, unit=None, status="RUNNING"):
        check_content_version(self.db, self.job)
        now = time.time()
        with self.db.connect() as connection:
            connection.execute(
                """UPDATE model_progress SET stage=?,status=?,completed_units=?,total_units=?,
                   unit=?,started_at=COALESCE(started_at,?),updated_at=? WHERE job_id=? AND model_id=?
                   AND content_version=? AND EXISTS(SELECT 1 FROM jobs WHERE id=? AND content_version=?)""",
                (
                    stage,
                    status,
                    completed,
                    total,
                    unit,
                    now,
                    now,
                    self.job["id"],
                    model_id,
                    self.job.get("content_version", 0),
                    self.job["id"],
                    self.job.get("content_version", 0),
                ),
            )
            connection.execute(
                "UPDATE jobs SET updated_at=? WHERE id=? AND content_version=?",
                (now, self.job["id"], self.job.get("content_version", 0)),
            )
        previous, last_logged = self.logs.get(model_id, (None, 0))
        if (
            previous != stage
            or now - last_logged >= 5
            or (total is not None and completed >= total)
        ):
            log.info(
                "model_progress job_id=%s model_id=%s stage=%s status=%s completed=%s total=%s unit=%s",
                self.job["id"],
                model_id,
                stage,
                status,
                completed,
                total,
                unit,
            )
            self.logs[model_id] = (stage, now)

    def callback(self, model_id):
        return lambda stage, completed=0, total=None, unit=None: self.update(
            model_id, stage, completed, total, unit
        )

    def start_batch(self, model_id, index, count):
        check_content_version(self.db, self.job)
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE model_progress SET batch_index=?,batch_documents=?,completed_units=0,total_units=NULL,unit=NULL WHERE job_id=? AND model_id=? AND content_version=?",
                (index, count, self.job["id"], model_id, self.job.get("content_version", 0)),
            )
        self.update(model_id, "LOADING_MODEL")

    def complete_batch(self, model_id, count):
        check_content_version(self.db, self.job)
        with self.db.connect() as connection:
            connection.execute(
                """UPDATE model_progress SET completed_documents=min(total_documents,completed_documents+?),
                   status=CASE WHEN completed_documents+failed_documents+?>=total_documents THEN
                   CASE WHEN failed_documents>0 THEN 'COMPLETED_WITH_ERRORS' ELSE 'COMPLETED' END
                   ELSE 'WAITING' END,stage='WAITING',updated_at=? WHERE job_id=? AND model_id=? AND content_version=?""",
                (
                    count,
                    count,
                    time.time(),
                    self.job["id"],
                    model_id,
                    self.job.get("content_version", 0),
                ),
            )
        log.info(
            "model_batch_completed job_id=%s model_id=%s documents=%s",
            self.job["id"],
            model_id,
            count,
        )

    def fail(self, model_id, error, count=None):
        check_content_version(self.db, self.job)
        with self.db.connect() as connection:
            connection.execute(
                """UPDATE model_progress SET status='FAILED',stage='FAILED',error_code=?,
                   failed_documents=min(total_documents-completed_documents,failed_documents+COALESCE(?,total_documents)),
                   updated_at=? WHERE job_id=? AND model_id=? AND content_version=?""",
                (
                    type(error).__name__,
                    count,
                    time.time(),
                    self.job["id"],
                    model_id,
                    self.job.get("content_version", 0),
                ),
            )

    def restore_document(self, metadata):
        """Recover member outcomes from a validated publication, once per member."""
        check_content_version(self.db, self.job)
        members = {row["model_id"]: row for row in metadata if row.get("model_id")}
        with self.db.connect() as connection:
            for identity, row in members.items():
                failed = row.get("status") == "FAILED"
                connection.execute(
                    """UPDATE model_progress SET
                       completed_documents=min(total_documents,completed_documents+?),
                       failed_documents=min(total_documents-min(total_documents,completed_documents+?),failed_documents+?),
                       error_code=COALESCE(error_code,?),status='WAITING',stage='WAITING',updated_at=?
                       WHERE job_id=? AND model_id=? AND content_version=? AND status!='FAILED'""",
                    (
                        int(not failed),
                        int(not failed),
                        int(failed),
                        row.get("error_code") if failed else None,
                        time.time(),
                        self.job["id"],
                        identity,
                        self.job.get("content_version", 0),
                    ),
                )

    def finish(self):
        check_content_version(self.db, self.job)
        with self.db.connect() as connection:
            connection.execute(
                """UPDATE model_progress SET status=CASE WHEN error_code IS NOT NULL THEN
                   CASE WHEN completed_documents>0 THEN 'COMPLETED_WITH_ERRORS' ELSE 'FAILED' END
                   WHEN completed_documents=0 AND kind='NORMALIZATION' THEN 'SKIPPED' ELSE 'COMPLETED' END,
                   stage='FINISHED',updated_at=? WHERE job_id=? AND content_version=?""",
                (time.time(), self.job["id"], self.job.get("content_version", 0)),
            )

    @staticmethod
    def snapshot(database, job, total_documents=None):
        with database.connect() as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM model_progress WHERE job_id=? AND content_version=? ORDER BY kind,model_id",
                    (job["id"], job.get("content_version", 0)),
                )
            ]
        if not rows and job["status"] in ("QUEUED", "PROCESSING"):
            payload = json.loads(job["payload"])
            for model in payload.get("selected_models", []):
                rows.append(
                    {
                        "model_id": model["model_id"],
                        "kind": "NER",
                        "status": "PENDING",
                        "stage": "PENDING",
                        "completed_documents": 0,
                        "failed_documents": 0,
                        "total_documents": total_documents
                        if total_documents is not None
                        else job["document_count"],
                        "batch_index": 0,
                        "batch_count": 0,
                        "batch_documents": 0,
                        "completed_units": 0,
                        "total_units": None,
                        "unit": None,
                        "started_at": None,
                        "updated_at": None,
                        "error_code": None,
                    }
                )
        for row in rows:
            done = row["completed_documents"] + row["failed_documents"]
            if (
                row["stage"] in ("INFERENCE", "DECODING")
                and row["status"] == "RUNNING"
                and row["total_units"]
            ):
                done += row["batch_documents"] * min(1, row["completed_units"] / row["total_units"])
            row["progress_percent"] = (
                min(100, 100 * done / row["total_documents"]) if row["total_documents"] else 0
            )
            for key in ("updated_at", "started_at"):
                row[key] = (
                    datetime.fromtimestamp(row[key], timezone.utc).isoformat() if row[key] else None
                )
            for key in ("job_id", "content_version"):
                row.pop(key, None)
        return rows

    @staticmethod
    def interrupt(database, job, error_code):
        with database.connect() as connection:
            connection.execute(
                """UPDATE model_progress SET status='FAILED',stage='FAILED',error_code=COALESCE(error_code,?),
                   updated_at=? WHERE job_id=? AND content_version=? AND status NOT IN
                   ('COMPLETED','COMPLETED_WITH_ERRORS','FAILED','SKIPPED') AND EXISTS
                   (SELECT 1 FROM jobs WHERE id=? AND content_version=? AND status NOT IN ('DELETED','EXPIRED'))""",
                (
                    error_code,
                    time.time(),
                    job["id"],
                    job.get("content_version", 0),
                    job["id"],
                    job.get("content_version", 0),
                ),
            )
