import secrets
import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import submit


def test_catalog_and_unconfigured_model(settings):
    with TestClient(create_app(settings)) as c:
        assert c.get("/").status_code == 200
        assert {x["code"] for x in c.get("/api/languages").json()} == {"es", "en"}
        assert not any(x["available"] for x in c.get("/api/models").json())
        assert submit(c).status_code == 422


@pytest.mark.parametrize(
    "fields",
    [
        {"submitter_name": " "},
        {"submitter_email": "broken"},
        {"language": "xx"},
        {"entities": []},
        {"entities": ["SYMPTOM"]},
        {"entities": ["DISEASE", "DISEASE"]},
        {"submitter_email": ""},
    ],
)
def test_form_validation(client, fields):
    assert submit(client, **fields).status_code == 422


def test_accept_and_status_no_inference(client):
    response = submit(client)
    assert response.status_code == 202
    data = response.json()
    assert len(data["token"]) == 43
    status = client.get("/api/jobs/" + data["token"])
    assert status.json()["status"] == "QUEUED"
    assert "submitter_email" not in status.json()
    assert status.headers["cache-control"] == "no-store"
    assert status.headers["referrer-policy"] == "no-referrer"
    assert client.get("/jobs/" + data["token"]).status_code == 200
    assert client.get(f"/api/jobs/{data['token']}/download/brat").status_code == 409
    assert client.get(f"/api/jobs/{data['token']}/statistics").status_code == 409
    assert client.get("/api/jobs/" + secrets.token_urlsafe(32)).status_code == 404
    assert client.get("/api/jobs/bad").status_code == 404
    db = client.app.state.db
    with db.connect() as c:
        assert c.execute("SELECT token_hash FROM jobs").fetchone()[0] != data["token"]
    limited = submit(client, submitter_email="different@example.org")
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    # Forwarded headers cannot change IP with TestClient/no trusted proxy middleware.
    assert (
        client.post(
            "/api/jobs",
            data={
                "submitter_name": "X",
                "submitter_email": "third@example.org",
                "language": "es",
                "entities": ["DISEASE"],
            },
            files={"files": ("b.txt", b"abc")},
            headers={"X-Forwarded-For": "9.8.7.6"},
        ).status_code
        == 429
    )


def test_expired_downloads(client):
    data = submit(client).json()
    with client.app.state.db.connect() as c:
        c.execute("UPDATE jobs SET status='COMPLETED',expires_at=?", (time.time() - 1,))
    for suffix in ("", "/download/brat", "/download/tsv", "/statistics"):
        assert client.get("/api/jobs/" + data["token"] + suffix).status_code == 410


def test_origins_body_limits(client):
    assert client.post("/api/jobs", headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert (
        client.post("/api/jobs", headers={"Content-Length": str(100 * 1024**2)}).status_code == 413
    )
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 503
    client.app.state.db.heartbeat()
    assert client.get("/ready").status_code == 200


def test_storage_error_does_not_expose_private_paths(client, monkeypatch):
    def broken_loader(*args, **kwargs):
        raise OSError("/private/patient-sensitive-filename")

    monkeypatch.setattr("app.services.jobs.ingest", broken_loader)
    response = submit(client)
    assert response.status_code == 503
    assert "patient-sensitive" not in response.text
