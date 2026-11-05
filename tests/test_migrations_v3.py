import subprocess

from app.db import Database
from tests.conftest import enqueue


def test_old_capabilities_and_deadlines_survive_additive_upgrade(settings):
    source = subprocess.check_output(["git", "show", "9c95bb5:app/db.py"], text=True)
    namespace = {}
    exec(compile(source, "baseline-db.py", "exec"), namespace)
    old = namespace["Database"](settings.model_copy(update={"job_results_ttl_hours": 24}))
    token = enqueue(old)
    old.claim()
    old.finish("job1", {"documents": 1})
    before = old.get(token)
    current = Database(settings)
    after = current.get(token)
    assert after["token_hash"] == before["token_hash"]
    assert after["expires_at"] == before["expires_at"]
    assert after["status"] == before["status"] == "COMPLETED"
    with current.connect() as c:
        assert c.execute("SELECT version FROM schema_migrations").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
    Database(settings)
    assert current.get(token)["expires_at"] == before["expires_at"]


def test_admission_does_not_scan_terminal_directories(settings, monkeypatch):
    db = Database(settings)
    enqueue(db)
    db.finish("job1", {"documents": 1})
    monkeypatch.setattr(
        "app.db.directory_bytes",
        lambda _: (_ for _ in ()).throw(AssertionError("Admission scanned disk")),
    )
    lease = db.reserve_upload()
    db.release_upload(lease)
