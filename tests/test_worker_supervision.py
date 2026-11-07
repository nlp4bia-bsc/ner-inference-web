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


def test_timeout_covers_child_shutdown(settings, caplog):
    settings = settings.model_copy(update={"job_timeout_seconds": 1})
    storage, db = LocalStorage(settings.storage_root), Database(settings)
    enqueue(db)
    job = db.claim()
    storage.job(job["id"]).mkdir()
    started = time.monotonic()
    ok, summary = execute(job, settings, db, storage, target=stuck_after_result)
    assert not ok and summary is None
    assert "reason=JobTimeout" in caplog.text
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


def test_content_change_interrupts_spawned_worker_and_cannot_complete_stale_result(settings):
    from threading import Thread

    storage, db = LocalStorage(settings.storage_root), Database(settings)
    enqueue(db)
    job = db.claim()
    storage.job(job["id"]).mkdir()

    def change_content():
        time.sleep(0.5)
        with db.connect() as connection:
            connection.execute(
                "UPDATE jobs SET content_version=content_version+1 WHERE id=?", (job["id"],)
            )

    thread = Thread(target=change_content)
    thread.start()
    started = time.monotonic()
    ok, summary = execute(job, settings, db, storage, target=stuck_after_result)
    thread.join()
    assert not ok and summary is None and time.monotonic() - started < 10
    db.finish(job["id"], summary, failed=True, claimed_version=job["content_version"])
    with db.connect() as connection:
        current = connection.execute(
            "SELECT status,attempts FROM jobs WHERE id=?", (job["id"],)
        ).fetchone()
    assert current["status"] == "QUEUED" and current["attempts"] == 0
    assert not (storage.job(job["id"]) / "worker-summary.json").exists()
