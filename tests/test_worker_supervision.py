"""Exercise spawned child processes, including results larger than an OS pipe buffer."""

import json
import time
from pathlib import Path

from app.db import Database
from app.storage import LocalStorage
from app.worker import execute
from tests.conftest import enqueue


def large_result(job, settings, parent_pid):
    path = Path(settings["storage_root"]) / "jobs" / job["id"] / "worker-summary.json"
    path.write_text(json.dumps({"models": "x" * 1024 * 1024}))


def stuck_after_result(job, settings, parent_pid):
    large_result(job, settings, parent_pid)
    time.sleep(60)


def no_result(job, settings, parent_pid):
    pass


def test_large_result_does_not_block_supervisor(settings):
    storage, db = LocalStorage(settings.storage_root), Database(settings)
    enqueue(db)
    job = db.claim()
    storage.job(job["id"]).mkdir()
    ok, summary = execute(job, settings, db, storage, target=large_result)
    assert ok and len(summary["models"]) == 1024 * 1024
    assert not (storage.job(job["id"]) / "worker-summary.json").exists()


def test_timeout_covers_child_shutdown(settings):
    settings = settings.model_copy(update={"job_timeout_seconds": 1})
    storage, db = LocalStorage(settings.storage_root), Database(settings)
    enqueue(db)
    job = db.claim()
    storage.job(job["id"]).mkdir()
    started = time.monotonic()
    ok, summary = execute(job, settings, db, storage, target=stuck_after_result)
    assert not ok and summary is None
    assert time.monotonic() - started < 10
    assert not (storage.job(job["id"]) / "worker-summary.json").exists()


def test_stale_result_cannot_complete_a_retry(settings):
    storage, db = LocalStorage(settings.storage_root), Database(settings)
    enqueue(db)
    job = db.claim()
    storage.job(job["id"]).mkdir()
    (storage.job(job["id"]) / "worker-summary.json").write_text('{"old": true}')
    ok, summary = execute(job, settings, db, storage, target=no_result)
    assert not ok and summary is None
