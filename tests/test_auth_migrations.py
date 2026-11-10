"""Upgrade an actual previous database copy and recover a failed transactional DDL."""

import sqlite3
import subprocess
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from app.db import Database
from app.persistence import migrations
from tests.conftest import enqueue


def previous_db(settings):
    namespace = {}
    source = subprocess.check_output(["git", "show", "b8d4d4f:app/db.py"], text=True)
    exec(compile(source, "v3-db.py", "exec"), namespace)

    def prior(db):
        migrations._migration_one(db)
        migrations._migration_two(db)

    with patch.object(migrations, "migrate", prior):
        old = namespace["Database"](settings)
    token = enqueue(old)
    old.claim()
    old.finish("job1", {"documents": 1})
    return old, token


def test_v4_upgrade_on_previous_copy_preserves_jobs_fifo_offsets_and_deadlines(settings, tmp_path):
    old, token = previous_db(settings)
    before = old.get(token)
    copy = settings.model_copy(update={"storage_root": tmp_path / "copy"})
    copy.storage_root.mkdir()
    with old.connect() as source, sqlite3.connect(copy.db_path) as target:
        source.backup(target)
    upgraded = Database(copy)
    after = upgraded.get(token)
    assert all(after[key] == value for key, value in before.items())
    assert after["owner_user_id"] is None
    Database(copy)
    with upgraded.connect() as c:
        assert [
            r[0] for r in c.execute("SELECT version FROM schema_migrations ORDER BY version")
        ] == [1, 2, 3, 4, 5, 6]
        assert c.execute("SELECT count(*) FROM users").fetchone()[0] == 0
        assert c.execute("SELECT seq FROM jobs").fetchone()[0] == before["seq"]


def test_failed_auth_migration_rolls_back_and_retries(settings, monkeypatch):
    old, token = previous_db(settings)
    before = old.get(token)
    original = old.connect

    class Fault:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, *args):
            if "CREATE TABLE sessions" in sql:
                raise RuntimeError("Injected migration interruption")
            return self.connection.execute(sql, *args)

    @contextmanager
    def broken():
        with original() as c:
            yield Fault(c)

    monkeypatch.setattr(old, "connect", broken)
    with pytest.raises(RuntimeError):
        migrations._migration_three(old)
    with original() as c:
        assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone()
        assert not c.execute("SELECT 1 FROM schema_migrations WHERE version=3").fetchone()
    current = Database(settings)
    assert current.get(token)["expires_at"] == before["expires_at"]


def test_approval_upgrade_preserves_existing_admin_and_its_mfa_session(settings):
    import secrets
    import time

    from fastapi.testclient import TestClient

    from app.auth.email import cipher
    from app.auth.passwords import hash_password
    from app.main import create_app

    settings = settings.model_copy(
        update={"require_email_verification": False, "mail_backend": "none"}
    )
    with patch.object(migrations, "_migration_six", lambda _: None):
        old = Database(settings)
    identity, token, now = "existing-admin", secrets.token_urlsafe(32), time.time()
    password_hash = hash_password("Existing password")
    mfa_secret = cipher(old, "mfa-secret-v1").encrypt(b"SYNTHETICMFASECRET").decode()
    with old.connect() as connection:
        connection.execute(
            """INSERT INTO users(id,full_name,email,institution,professional_role,password_hash,
          created_at,updated_at,legal_accepted_at,system_role,mfa_enabled,mfa_secret)
          VALUES (?,?,?,?,?,?,?,?,?,'ADMIN',1,?)""",
            (
                identity,
                "Existing Admin",
                "existing@example.test",
                "Synthetic institute",
                "RESEARCHER",
                password_hash,
                now,
                now,
                now,
                mfa_secret,
            ),
        )
        connection.execute(
            """INSERT INTO sessions(token_hash,user_id,created_at,last_seen_at,expires_at,auth_version,csrf_seed,mfa_verified)
          VALUES (?,?,?,?,?,1,?,1)""",
            (old.token_hash(token), identity, now, now, now + 3600, secrets.token_urlsafe(32)),
        )
    app = create_app(settings)
    with TestClient(app) as administrator:
        administrator.cookies.set(settings.session_cookie, token)
        assert administrator.get("/api/admin/users").status_code == 200
        profile = administrator.get("/api/profile").json()
        assert profile["approval_status"] == "APPROVED" and profile["document_limit"] is None
        assert profile["system_role"] == "ADMIN"
    Database(settings)
    with old.connect() as connection:
        current = connection.execute("SELECT * FROM users WHERE id=?", (identity,)).fetchone()
        assert current["password_hash"] == password_hash and current["mfa_secret"] == mfa_secret
        assert current["auth_version"] == 1
        assert (
            connection.execute("SELECT count(*) FROM schema_migrations WHERE version=6").fetchone()[
                0
            ]
            == 1
        )


def test_approval_migration_is_transactional_and_retryable(settings, monkeypatch):
    with patch.object(migrations, "_migration_six", lambda _: None):
        old = Database(settings)
    original = old.connect

    class Fault:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, *args):
            if "ADD COLUMN document_limit" in sql:
                raise RuntimeError("Synthetic migration interruption")
            return self.connection.execute(sql, *args)

    @contextmanager
    def interrupted():
        with original() as connection:
            yield Fault(connection)

    monkeypatch.setattr(old, "connect", interrupted)
    with pytest.raises(RuntimeError):
        migrations._migration_six(old)
    with original() as connection:
        assert "approval_status" not in {
            row[1] for row in connection.execute("PRAGMA table_info(users)")
        }
        assert not connection.execute("SELECT 1 FROM schema_migrations WHERE version=6").fetchone()
    upgraded = Database(settings)
    with upgraded.connect() as connection:
        assert {"approval_status", "document_limit"} <= {
            row[1] for row in connection.execute("PRAGMA table_info(users)")
        }
