import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db import Database
from app.errors import ServiceError
from app.services.cleanup import cleanup
from app.storage import LocalStorage
from tests.conftest import enqueue


def test_fifo_restart_and_recovery(settings):
    db = Database(settings)
    for i in range(4):
        enqueue(db, f"job{i}", str(i), f"{i}@example.org")
    assert db.claim()["id"] == "job0"
    restarted = Database(settings)
    restarted.recover()
    assert restarted.claim()["id"] == "job0"
    restarted.recover()  # attempt 2 interrupted => bounded failure
    assert restarted.claim()["id"] == "job1"
    with restarted.connect() as c:
        assert c.execute("SELECT status FROM jobs WHERE id='job0'").fetchone()[0] == "FAILED"
        events = [
            r[0] for r in c.execute("SELECT status FROM events WHERE job_id='job0' ORDER BY seq")
        ]
    assert events == ["QUEUED", "PROCESSING", "QUEUED", "PROCESSING", "FAILED"]


def test_atomic_rate_limit(settings):
    db = Database(settings)

    def attempt(i):
        try:
            enqueue(db, f"job{i}", "same-ip", f"{i}@example.org")
            return True
        except ServiceError as exc:
            assert exc.status == 429
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(8))) == 1


def test_email_limit_and_later_acceptance(settings):
    db = Database(settings)
    enqueue(db, "one", "ip1")
    with pytest.raises(ServiceError) as error:
        enqueue(db, "two", "ip2")
    assert error.value.status == 429
    with db.connect() as c:
        c.execute("UPDATE limits SET accepted_at=?", (time.time() - 61,))
    enqueue(db, "two", "ip2")


def test_queue_capacity(settings):
    db = Database(settings.model_copy(update={"max_queue_size": 1}))
    enqueue(db)
    with pytest.raises(ServiceError) as error:
        enqueue(db, "job2", "new", "new@example.org")
    assert error.value.status == 503


def test_upload_leases_storage(settings):
    db = Database(settings.model_copy(update={"max_concurrent_uploads": 1}))
    lease = db.reserve_upload()
    with pytest.raises(ServiceError):
        db.reserve_upload()
    db.release_upload(lease)
    assert db.reserve_upload()
    with pytest.raises(ServiceError):
        Database(settings.model_copy(update={"max_storage_mb": 1})).reserve_upload()


def test_retention_and_cleanup(settings):
    db, storage = Database(settings), LocalStorage(settings.storage_root)
    token = enqueue(db)
    root = storage.job("job1")
    root.mkdir()
    (root / "patient.txt").write_text("Sensitive")
    db.claim()
    db.finish("job1", {"documents": 1})
    job = db.get(token)
    assert job["expires_at"] - job["completed_at"] == 24 * 3600
    with db.connect() as c:
        c.execute("UPDATE jobs SET expires_at=?", (time.time() - 1,))
    cleanup(db, storage)
    job = db.get(token)
    assert job["status"] == "EXPIRED" and not root.exists()
    assert json.loads(job["payload"]) == {}


def test_atomic_claims(settings):
    db = Database(settings)
    enqueue(db)
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: db.claim(), range(8)))
    assert sum(x is not None for x in claims) == 1
