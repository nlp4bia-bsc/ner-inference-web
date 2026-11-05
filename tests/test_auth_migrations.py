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
        ] == [1, 2, 3]
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
