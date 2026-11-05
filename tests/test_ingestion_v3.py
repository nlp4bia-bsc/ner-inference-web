from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import request_data


@pytest.mark.parametrize("text", ["😀 é e\u0301\r\n漢字\tend", "<script>text</script>"])
def test_pasted_text_preserves_exact_bytes(settings, text):
    with TestClient(create_app(settings)) as client:
        client.app.state.registry.languages["es"]["entities"]["DISEASE"]["available"] = True
        response = client.post(
            "/api/jobs", data={**request_data(), "input_mode": "PASTED_TEXT", "pasted_text": text}
        )
        assert response.status_code == 202
        job = client.app.state.db.get(response.json()["token"])
        assert (
            settings.storage_root / "jobs" / job["id"] / "input" / "pasted-text.txt"
        ).read_bytes() == text.encode()
        from app.persistence.progress import ProgressRepository

        assert (
            ProgressRepository(client.app.state.db).rows(job["id"])[0]["source_type"]
            == "PASTED_TEXT"
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"pasted_text": " "},
        {"pasted_text": "abc", "document_name": "../bad.txt"},
        {"input_mode": "unknown", "pasted_text": "abc"},
    ],
)
def test_invalid_paste(settings, fields):
    with TestClient(create_app(settings)) as client:
        client.app.state.registry.languages["es"]["entities"]["DISEASE"]["available"] = True
        assert client.post("/api/jobs", data={**request_data(), **fields}).status_code == 422


def test_paste_and_files_are_mutually_exclusive(client):
    response = client.post(
        "/api/jobs",
        data={**request_data(), "pasted_text": "abc"},
        files={"files": ("a.txt", b"abc")},
    )
    assert response.status_code == 422


def test_concurrent_real_http_admission_and_durable_fifo(settings):
    settings = settings.model_copy(update={"max_concurrent_uploads": 8})
    app = create_app(settings)
    app.state.registry.languages["es"]["entities"]["DISEASE"]["available"] = True

    def send(i):
        with TestClient(app, client=(f"10.0.0.{i + 1}", 1234)) as client:
            return client.post(
                "/api/jobs",
                data=request_data(submitter_email=f"{i}@example.org"),
                files={"files": (f"{i}.txt", b"abc")},
            ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(send, range(8))) == [202] * 8
    with app.state.db.connect() as c:
        order = [r[0] for r in c.execute("SELECT id FROM jobs ORDER BY seq")]
        assert c.execute("SELECT count(*) FROM uploads").fetchone()[0] == 0
    assert [app.state.db.claim()["id"] for _ in range(8)] == order


def test_actual_body_limit_without_content_length_and_lease_cleanup(settings):
    settings = settings.model_copy(update={"max_upload_mb": 0.001})
    app = create_app(settings)
    with TestClient(app) as client:

        def chunks():
            for _ in range(20):
                yield b"a" * 65536

        response = client.post(
            "/api/jobs", content=chunks(), headers={"Content-Type": "application/octet-stream"}
        )
        assert response.status_code == 413
        with app.state.db.connect() as c:
            assert c.execute("SELECT count(*) FROM uploads").fetchone()[0] == 0
        assert not list((settings.storage_root / "staging").iterdir())


def test_active_upload_staging_survives_cleanup(settings):
    import os
    import time

    from app.db import Database
    from app.services.cleanup import cleanup
    from app.storage import LocalStorage

    db, storage = Database(settings), LocalStorage(settings.storage_root)
    lease = db.reserve_upload()
    db.touch_upload(lease, "active-staging")
    directory = settings.storage_root / "staging" / "active-staging"
    directory.mkdir()
    os.utime(directory, (time.time() - 3600, time.time() - 3600))
    cleanup(db, storage)
    assert directory.exists()
    db.release_upload(lease)
    cleanup(db, storage)
    assert not directory.exists()
