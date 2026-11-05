"""SQLite is the durable FIFO, state machine and atomic admission controller."""

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import time
import uuid
from contextlib import contextmanager

from app.config import Settings
from app.errors import ServiceError
from app.storage import directory_bytes


class Database:
    def __init__(self, settings: Settings):
        self.s = settings
        settings.storage_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS jobs (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, token_hash TEXT UNIQUE,
              status TEXT NOT NULL, payload TEXT NOT NULL, document_count INTEGER NOT NULL,
              processed_documents INTEGER DEFAULT 0, created_at REAL NOT NULL, started_at REAL,
              completed_at REAL, expires_at REAL, error_summary TEXT, attempts INTEGER DEFAULT 0,
              summary TEXT, expired_at REAL);
            CREATE TABLE IF NOT EXISTS events (
              seq INTEGER PRIMARY KEY, job_id TEXT, status TEXT, at REAL);
            CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, accepted_at REAL);
            CREATE TABLE IF NOT EXISTS uploads (id TEXT PRIMARY KEY, created_at REAL);
            CREATE TABLE IF NOT EXISTS runtime (key TEXT PRIMARY KEY, value REAL);
            CREATE INDEX IF NOT EXISTS queue ON jobs(status,seq);
            """)
            c.execute("INSERT OR IGNORE INTO runtime VALUES ('secret_created', ?)", (time.time(),))
        from app.persistence.migrations import migrate

        migrate(self)
        # Persistent keyed hashes prevent offline guessing of IP/email rate-limit keys.
        secret_path = settings.storage_root / "rate-key"
        temporary = settings.storage_root / ("rate-key-" + uuid.uuid4().hex)
        temporary.write_bytes(secrets.token_bytes(32))
        temporary.chmod(0o600)
        try:
            os.link(temporary, secret_path)
        except FileExistsError:
            pass
        finally:
            temporary.unlink()
        self.rate_key = secret_path.read_bytes()

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.s.db_path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def rate_hash(self, value: str) -> str:
        import hmac

        return hmac.new(self.rate_key, value.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def event(c, job_id: str, status: str, now: float):
        c.execute("INSERT INTO events(job_id,status,at) VALUES (?,?,?)", (job_id, status, now))

    def reservation(self, input_bytes: int) -> int:
        return int(
            input_bytes * self.s.storage_reserve_factor + self.s.storage_reserve_extra_mb * 1024**2
        )

    def capacity(self, c, additional: int, credit: int = 0):
        used = c.execute(
            "SELECT COALESCE(sum(CASE WHEN reserved_bytes>0 THEN max(storage_bytes,reserved_bytes) ELSE storage_bytes END),0) FROM jobs WHERE status!='EXPIRED'"
        ).fetchone()[0]
        uploads = c.execute("SELECT COALESCE(sum(reserved_bytes),0) FROM uploads").fetchone()[0]
        if used + uploads + additional - credit > self.s.max_storage_mb * 1024**2:
            raise ServiceError("Storage capacity is temporarily unavailable.", 503)
        reserved = c.execute("SELECT COALESCE(sum(reserved_bytes),0) FROM jobs").fetchone()[0]
        if (
            shutil.disk_usage(self.s.storage_root).free
            < self.s.min_free_disk_mb * 1024**2 + reserved + uploads + additional - credit
        ):
            raise ServiceError("Storage capacity is temporarily unavailable.", 503)

    def reserve_upload(self) -> str:
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if (
                c.execute("SELECT count(*) FROM uploads").fetchone()[0]
                >= self.s.max_concurrent_uploads
            ):
                raise ServiceError("The service is busy. Please try again shortly.", 503)
            reserve = 2 * self.s.upload_bytes + int(self.s.storage_reserve_extra_mb * 1024**2)
            self.capacity(c, reserve)
            key = uuid.uuid4().hex
            c.execute(
                "INSERT INTO uploads(id,created_at,reserved_bytes) VALUES (?,?,?)",
                (key, time.time(), reserve),
            )
            return key

    def resize_upload(self, key, reserve):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT reserved_bytes FROM uploads WHERE id=?", (key,)).fetchone()
            if not row:
                raise ServiceError("Upload lease expired; retry your submission.", 503)
            if reserve > row[0]:
                self.capacity(c, reserve - row[0])
                c.execute("UPDATE uploads SET reserved_bytes=? WHERE id=?", (reserve, key))

    def touch_upload(self, key, staging_id=None):
        with self.connect() as c:
            c.execute(
                "UPDATE uploads SET created_at=?,staging_id=COALESCE(?,staging_id) WHERE id=?",
                (time.time(), staging_id, key),
            )

    def release_upload(self, key: str):
        with self.connect() as c:
            c.execute("DELETE FROM uploads WHERE id=?", (key,))

    def accept(
        self, job_id: str, token: str, payload: dict, count: int, ip: str, lease: str | None = None
    ):
        now = time.time()
        keys = [self.rate_hash("ip:" + ip), self.rate_hash("email:" + payload["submitter_email"])]
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            for key in keys:
                row = c.execute("SELECT accepted_at FROM limits WHERE key=?", (key,)).fetchone()
                if row and now - row[0] < self.s.rate_limit_seconds:
                    wait = max(1, int(self.s.rate_limit_seconds - (now - row[0])) + 1)
                    raise ServiceError(
                        "You can submit one request per minute. Please try again shortly.",
                        429,
                        wait,
                    )
            n = c.execute(
                "SELECT count(*) FROM jobs WHERE status IN ('QUEUED','PROCESSING')"
            ).fetchone()[0]
            if n >= self.s.max_queue_size:
                raise ServiceError("The queue is full. Please try again later.", 503)
            references = payload.get("document_references", [])
            input_bytes = sum(r["size_bytes"] for r in references)
            reserve = self.reservation(input_bytes)
            upload = c.execute("SELECT reserved_bytes FROM uploads WHERE id=?", (lease,)).fetchone()
            self.capacity(c, reserve, upload[0] if upload else 0)
            c.execute(
                """INSERT INTO jobs(id,token_hash,status,payload,document_count,created_at)
                         VALUES (?,?,'QUEUED',?,?,?)""",
                (job_id, self.token_hash(token), json.dumps(payload), count, now),
            )
            c.execute(
                "UPDATE jobs SET storage_bytes=?,reserved_bytes=?,stage=?,updated_at=? WHERE id=?",
                (input_bytes, reserve, "QUEUED", now, job_id),
            )
            for r in references:
                c.execute(
                    "INSERT INTO documents(job_id,document_id,filename,source_type,size_bytes,updated_at) VALUES (?,?,?,?,?,?)",
                    (
                        job_id,
                        r["document_id"],
                        r["original_relative_path"],
                        r["source_type"],
                        r["size_bytes"],
                        now,
                    ),
                )
            if lease:
                c.execute("DELETE FROM uploads WHERE id=?", (lease,))
            for key in keys:
                c.execute("INSERT OR REPLACE INTO limits VALUES (?,?)", (key, now))
            self.event(c, job_id, "QUEUED", now)

    def get(self, token: str):
        if len(token) != 43 or not all(x.isalnum() or x in "-_" for x in token):
            raise ServiceError("Request not found.", 404)
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM jobs WHERE token_hash=?", (self.token_hash(token),)
            ).fetchone()
        if not row:
            raise ServiceError("Request not found.", 404)
        return dict(row)

    def recover(self):
        # Only called while holding the lifetime-exclusive worker lock.
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("UPDATE documents SET status='PENDING' WHERE status='PROCESSING'")
            for row in c.execute(
                "SELECT id,attempts FROM jobs WHERE status='PROCESSING'"
            ).fetchall():
                now = time.time()
                status = "QUEUED" if row["attempts"] < self.s.max_attempts else "FAILED"
                c.execute(
                    "UPDATE jobs SET status=?, error_summary=?, completed_at=?, expires_at=? WHERE id=?",
                    (
                        status,
                        "Processing was interrupted." if status == "FAILED" else None,
                        now if status == "FAILED" else None,
                        now + self.s.job_results_ttl_hours * 3600 if status == "FAILED" else None,
                        row["id"],
                    ),
                )
                c.execute(
                    "UPDATE jobs SET stage=?,updated_at=? WHERE id=?", (status, now, row["id"])
                )
                if status == "FAILED":
                    c.execute(
                        "UPDATE documents SET status='FAILED',error_code='INTERRUPTED' WHERE job_id=? AND status!='ANNOTATED'",
                        (row["id"],),
                    )
                    c.execute("UPDATE jobs SET reserved_bytes=0 WHERE id=?", (row["id"],))
                self.event(c, row["id"], status, now)

    def claim(self):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT * FROM jobs WHERE status='QUEUED' ORDER BY seq LIMIT 1"
            ).fetchone()
            if not row:
                return None
            now = time.time()
            c.execute(
                "UPDATE jobs SET status='PROCESSING',started_at=?,attempts=attempts+1 WHERE id=?",
                (now, row["id"]),
            )
            self.event(c, row["id"], "PROCESSING", now)
            return dict(row)

    def record_storage(self, job_id):
        stored = directory_bytes(self.s.storage_root / "jobs" / job_id)
        with self.connect() as c:
            c.execute("UPDATE jobs SET storage_bytes=? WHERE id=?", (stored, job_id))
        return stored

    def finish(self, job_id: str, summary: dict | None = None, failed: bool = False):
        now = time.time()
        status = (
            "FAILED"
            if failed
            else (
                "COMPLETED_WITH_ERRORS"
                if summary and summary.get("failed_documents", 0)
                else "COMPLETED"
            )
        )
        stored = directory_bytes(self.s.storage_root / "jobs" / job_id)
        with self.connect() as c:
            c.execute(
                """UPDATE jobs SET status=?,completed_at=?,expires_at=?,summary=?,
                      error_summary=?,processed_documents=CASE WHEN EXISTS(SELECT 1 FROM documents WHERE job_id=jobs.id) THEN (SELECT count(*) FROM documents WHERE job_id=jobs.id AND status='ANNOTATED') WHEN ? THEN 0 ELSE document_count END WHERE id=?""",
                (
                    status,
                    now,
                    now + self.s.job_results_ttl_hours * 3600,
                    json.dumps(summary) if summary else None,
                    "Processing failed. Please contact the service with your request ID."
                    if failed
                    else None,
                    failed,
                    job_id,
                ),
            )
            c.execute(
                "UPDATE jobs SET reserved_bytes=0,storage_bytes=?,stage=?,updated_at=? WHERE id=?",
                (stored, status, now, job_id),
            )
            if failed:
                c.execute(
                    "UPDATE documents SET status='FAILED',error_code='JOB_FAILED' WHERE job_id=? AND status IN ('PENDING','PROCESSING')",
                    (job_id,),
                )
            self.event(c, job_id, status, now)

    def heartbeat(self):
        with self.connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO runtime VALUES ('worker_heartbeat',?)", (time.time(),)
            )
