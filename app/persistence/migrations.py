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
    _migration_three(database)
    _migration_four(database)
    _migration_five(database)
    _migration_six(database)


def _migration_three(database):
    """All DDL is transactional, including the ledger; historical jobs remain unowned."""
    statements = [
        """CREATE TABLE users(id TEXT PRIMARY KEY, full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE, institution TEXT NOT NULL, professional_role TEXT NOT NULL,
        professional_role_other TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,
        email_verified_at REAL, account_status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(account_status IN ('ACTIVE','SUSPENDED')),
        system_role TEXT NOT NULL DEFAULT 'USER' CHECK(system_role IN ('USER','ADMIN')),
        access_tier TEXT NOT NULL DEFAULT 'STANDARD' CHECK(access_tier IN ('STANDARD','EXTENDED','UNLIMITED')),
        preferred_locale TEXT NOT NULL DEFAULT 'en', created_at REAL NOT NULL,updated_at REAL NOT NULL,
        legal_accepted_at REAL NOT NULL, auth_version INTEGER NOT NULL DEFAULT 1,
        mfa_secret TEXT,mfa_enabled INTEGER NOT NULL DEFAULT 0,mfa_last_counter INTEGER DEFAULT -1,
        mfa_recovery_hashes TEXT NOT NULL DEFAULT '[]')""",
        """CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,
        created_at REAL NOT NULL,last_seen_at REAL NOT NULL,expires_at REAL NOT NULL,
        revoked_at REAL,auth_version INTEGER NOT NULL,csrf_seed TEXT NOT NULL,mfa_verified INTEGER DEFAULT 0)""",
        "CREATE INDEX session_owner ON sessions(user_id)",
        *[
            f"""CREATE TABLE {table}(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,
        created_at REAL NOT NULL,expires_at REAL NOT NULL,used_at REAL,revoked_at REAL,auth_version INTEGER NOT NULL)"""
            for table in ("email_verifications", "password_resets")
        ],
        """CREATE TABLE audit_events(id INTEGER PRIMARY KEY AUTOINCREMENT,actor_user_id TEXT,
        target_user_id TEXT,action TEXT NOT NULL,at REAL NOT NULL,details TEXT NOT NULL DEFAULT '{}')""",
        "CREATE INDEX audit_time ON audit_events(at)",
        """CREATE TABLE auth_limits(key TEXT PRIMARY KEY,window_start REAL NOT NULL,attempts INTEGER NOT NULL)""",
        """CREATE TABLE mfa_setups(user_id TEXT PRIMARY KEY,secret TEXT NOT NULL,expires_at REAL NOT NULL)""",
        """CREATE TABLE mail_outbox(id TEXT PRIMARY KEY,payload TEXT NOT NULL,created_at REAL NOT NULL,
        expires_at REAL NOT NULL,next_attempt REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'PENDING')""",
        "ALTER TABLE jobs ADD COLUMN owner_user_id TEXT",
        "CREATE INDEX job_owner ON jobs(owner_user_id,seq)",
    ]
    with database.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT 1 FROM schema_migrations WHERE version=3").fetchone():
            return
        for statement in statements:
            c.execute(statement)
        c.execute("INSERT INTO schema_migrations VALUES (3,?)", (time.time(),))


def _migration_four(database):
    import json
    import uuid

    with database.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT 1 FROM schema_migrations WHERE version=4").fetchone():
            return
        c.execute("ALTER TABLE jobs ADD COLUMN content_version INTEGER NOT NULL DEFAULT 0")
        c.execute("ALTER TABLE jobs ADD COLUMN processing_version INTEGER NOT NULL DEFAULT 0")
        c.execute("""CREATE TABLE upload_ledger(id INTEGER PRIMARY KEY AUTOINCREMENT,
          owner_user_id TEXT NOT NULL,job_id TEXT NOT NULL,document_id TEXT NOT NULL,
          filename TEXT NOT NULL,language TEXT,size_bytes INTEGER,uploaded_at REAL NOT NULL,
          state TEXT NOT NULL DEFAULT 'STORED',removed_at REAL,UNIQUE(job_id,document_id))""")
        c.execute(
            "CREATE INDEX upload_owner_state ON upload_ledger(owner_user_id,state,uploaded_at)"
        )
        for job in c.execute("SELECT * FROM jobs WHERE owner_user_id IS NOT NULL").fetchall():
            payload = json.loads(job["payload"])
            rows = c.execute(
                "SELECT * FROM documents WHERE job_id=? ORDER BY filename", (job["id"],)
            ).fetchall()
            expired = (
                job["status"] == "EXPIRED"
                or job["expires_at"] is not None
                and job["expires_at"] <= time.time()
            )
            for index in range(max(len(rows), job["document_count"])):
                row = dict(rows[index]) if index < len(rows) else {}
                identity = (
                    row.get("document_id")
                    or uuid.uuid5(uuid.NAMESPACE_URL, job["id"] + ":" + str(index)).hex
                )
                c.execute(
                    "INSERT OR IGNORE INTO upload_ledger(owner_user_id,job_id,document_id,filename,language,size_bytes,uploaded_at,state,removed_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        job["owner_user_id"],
                        job["id"],
                        identity,
                        row.get("filename", "Historical document"),
                        payload.get("language"),
                        row.get("size_bytes"),
                        job["created_at"],
                        "EXPIRED" if expired else "STORED",
                        job["expired_at"] if expired else None,
                    ),
                )
        c.execute("INSERT INTO schema_migrations VALUES (4,?)", (time.time(),))


def _migration_five(database):
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM schema_migrations WHERE version=5").fetchone():
            return
        connection.execute("""CREATE TABLE model_progress(
          job_id TEXT NOT NULL,model_id TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'NER',
          content_version INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'PENDING',
          stage TEXT NOT NULL DEFAULT 'PENDING',completed_documents INTEGER NOT NULL DEFAULT 0,
          failed_documents INTEGER NOT NULL DEFAULT 0,total_documents INTEGER NOT NULL,
          batch_index INTEGER NOT NULL DEFAULT 0,batch_count INTEGER NOT NULL DEFAULT 0,
          batch_documents INTEGER NOT NULL DEFAULT 0,completed_units INTEGER NOT NULL DEFAULT 0,
          total_units INTEGER,unit TEXT,started_at REAL,updated_at REAL NOT NULL,
          error_code TEXT,PRIMARY KEY(job_id,model_id))""")
        connection.execute("INSERT INTO schema_migrations VALUES(5,?)", (time.time(),))


def _migration_six(database):
    """Grandfather existing accounts; public registration explicitly creates PENDING requests."""
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM schema_migrations WHERE version=6").fetchone():
            return
        for statement in (
            "ALTER TABLE users ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'APPROVED' CHECK(approval_status IN ('PENDING','APPROVED','REJECTED','DELETING'))",
            "ALTER TABLE users ADD COLUMN approval_reviewed_at REAL",
            "ALTER TABLE users ADD COLUMN approval_reviewed_by TEXT",
            "ALTER TABLE users ADD COLUMN document_limit INTEGER CHECK(document_limit IS NULL OR document_limit>=0)",
            "CREATE INDEX user_approval ON users(approval_status,created_at)",
        ):
            connection.execute(statement)
        connection.execute("INSERT INTO schema_migrations VALUES(6,?)", (time.time(),))
