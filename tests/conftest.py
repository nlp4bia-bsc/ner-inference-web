import secrets

import pytest

from app.config import Settings
from app.main import create_app
from tests.auth_helpers import AccountClient as TestClient


@pytest.fixture
def settings(tmp_path):
    return Settings(
        storage_root=tmp_path / "storage",
        model_config_path="catalog/models.yaml",
        min_free_disk_mb=0,
        app_env="test",
        cookie_secure=False,
        mail_backend="memory",
    )


@pytest.fixture
def client(settings):
    app = create_app(settings)
    # Test-only availability; no application flag can select a fake inference adapter.
    app.state.registry.languages["es"]["entities"]["DISEASE"]["available"] = True
    with TestClient(app) as client:
        yield client


def request_data(**overrides):
    return {
        "submitter_name": "Researcher",
        "submitter_email": "user@example.org",
        "language": "es",
        "entities": ["DISEASE"],
        **overrides,
    }


def submit(client, **overrides):
    return client.post(
        "/api/jobs",
        data=request_data(**overrides),
        files=[("files", ("a.txt", b"Cancer.\r\n", "text/plain"))],
    )


def enqueue(db, job_id="job1", ip="127.0.0.1", email="a@example.org"):
    token = secrets.token_urlsafe(32)
    payload = {**request_data(submitter_email=email), "documents": ["a.txt"], "selected_models": []}
    db.accept(job_id, token, payload, 1, ip)
    return token
