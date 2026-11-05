"""Additive, versioned SQLite upgrades; existing tokens and deadlines are untouched."""

import time

from app.storage import directory_bytes


def _migration_one(database):
    with database.connect() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,applied_at REAL)"
        )
        if c.execute("SELECT 1 FROM schema_migrations WHERE version=1").fetchone():
            return
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT 1 FROM schema_migrations WHERE version=1").fetchone():
            return
        for name, definition in [
            ("stage", "TEXT DEFAULT 'QUEUED'"),
            ("updated_at", "REAL"),
            ("storage_bytes", "INTEGER DEFAULT 0"),
            ("reserved_bytes", "INTEGER DEFAULT 0"),
        ]:
            if name not in {r[1] for r in c.execute("PRAGMA table_info(jobs)")}:
                c.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        c.execute("ALTER TABLE uploads ADD COLUMN reserved_bytes INTEGER DEFAULT 0")
        c.execute("""CREATE TABLE documents(job_id TEXT,document_id TEXT,filename TEXT,source_type TEXT,
          size_bytes INTEGER,status TEXT DEFAULT 'PENDING',annotation_count INTEGER DEFAULT 0,
          entities_by_label TEXT DEFAULT '{}',statistics TEXT DEFAULT '{}',updated_at REAL,error_code TEXT,
          PRIMARY KEY(job_id,document_id))""")
        c.execute("CREATE INDEX documents_status ON documents(job_id,status)")
        # One-time reconciliation during the coordinated migration, never admission.
        for row in c.execute("SELECT id,payload,status FROM jobs").fetchall():
            size = directory_bytes(database.s.storage_root / "jobs" / row["id"])
            reserve = database.reservation(size) if row["status"] in ("QUEUED", "PROCESSING") else 0
            c.execute(
                "UPDATE jobs SET storage_bytes=?,reserved_bytes=?,updated_at=?,stage=? WHERE id=?",
                (size, reserve, time.time(), row["status"], row["id"]),
            )
        c.execute("INSERT INTO schema_migrations VALUES (1,?)", (time.time(),))


def _migration_two(database):
    with database.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT 1 FROM schema_migrations WHERE version=2").fetchone():
            return
        c.execute("ALTER TABLE uploads ADD COLUMN staging_id TEXT")
        c.execute("INSERT INTO schema_migrations VALUES (2,?)", (time.time(),))


def migrate(database):
    _migration_one(database)
    _migration_two(database)
