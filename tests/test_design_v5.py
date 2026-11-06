"""Security boundaries for the new workspace presentation and account actions."""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.ui_i18n import MESSAGES
from tests.auth_helpers import authenticate
from tests.conftest import submit
from tests.viewer_fixtures import seed_viewer


def test_shared_assets_and_new_pages_keep_default_deny(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        for path in ["/models", "/my-jobs", "/profile", "/sessions", "/account-deletion"]:
            assert client.get(path, follow_redirects=False).status_code == 303
        assert client.get("/api/auth/sessions").status_code == 401
        for path in [
            "/static/auth.css",
            "/static/auth.js",
            "/static/i18n.js",
            "/static/assets/bsc-blue.svg",
        ]:
            assert client.get(path).status_code == 200
        for path in [
            "/static/catalog.js",
            "/static/viewer.js",
            "/static/style.css",
            "/static/assets/../viewer.js",
        ]:
            assert client.get(path, follow_redirects=False).status_code == 303
        assert client.post("/account-deletion", json={}, follow_redirects=False).status_code == 303
    root = ET.fromstring(Path("app/static/assets/bsc-blue.svg").read_bytes())
    assert root.attrib["viewBox"] == "0 0 283.46 69.36"
    assert not any(
        node.tag.rsplit("}", 1)[-1] in ("script", "foreignObject") for node in root.iter()
    )
    assert not any(
        key.lower().startswith("on") or key.endswith("href")
        for node in root.iter()
        for key in node.attrib
    )


def test_workspace_metrics_and_history_are_owner_scoped(settings):
    app, accepted, _, _ = seed_viewer(settings)
    app.state.registry.languages["es"]["entities"]["DISEASE"]["available"] = True
    with TestClient(app) as owner, TestClient(app) as other:
        authenticate(owner, register=False)
        authenticate(other, "second@example.test")
        response = submit(other)
        assert response.status_code == 202
        foreign = response.json()["job_id"]
        own_history = owner.get("/api/my/jobs").json()
        assert [row["id"] for row in own_history] == [accepted["job_id"]]
        assert own_history[0]["name"] == "nested/sample.txt"
        assert own_history[0]["language"] == "es"
        assert foreign not in owner.get("/").text
        assert 'data-number="0"' in owner.get("/").text
        assert 'data-number="1"' in owner.get("/").text
        assert other.get("/api/jobs/" + accepted["job_id"]).status_code == 404
        assert owner.get("/api/jobs/" + foreign).status_code == 404
        assert owner.get("/admin").status_code == 403
        # Ordinary users cannot edit tier/role through the renewed profile.
        assert owner.patch("/api/profile", json={"access_tier": "UNLIMITED"}).status_code == 422


def test_sessions_and_deletion_request_never_expose_or_accept_another_identity(settings):
    app = create_app(settings)
    with TestClient(app) as first, TestClient(app) as second:
        first_user = authenticate(first, "first@example.test")
        second_user = authenticate(second, "second@example.test")
        sessions = first.get("/api/auth/sessions").json()
        assert len(sessions) == 1 and sessions[0]["current"] == 1
        assert set(sessions[0]) == {"created_at", "last_seen_at", "expires_at", "current"}
        for private in ["token_hash", "csrf_seed", "password_hash", second_user["id"]]:
            assert private not in first.get("/sessions").text
        csrf = first.headers.pop("X-CSRF-Token")
        assert first.post("/account-deletion", json={}).status_code == 403
        first.headers["X-CSRF-Token"] = csrf
        assert (
            first.post("/account-deletion", json={"owner_user_id": second_user["id"]}).status_code
            == 422
        )
        response = first.post("/account-deletion", json={})
        assert response.status_code == 200 and "has been recorded" in response.text
        assert first.get("/api/profile").json()["account_status"] == "ACTIVE"
        with app.state.db.connect() as c:
            row = c.execute(
                "SELECT actor_user_id,target_user_id FROM audit_events WHERE action='ACCOUNT_DELETION_REQUESTED'"
            ).fetchone()
            assert tuple(row) == (first_user["id"], first_user["id"])
        assert second.get("/api/auth/sessions").json()[0]["current"] == 1


def test_browser_vocabulary_is_complete_and_matches_server_source():
    for key, values in MESSAGES.items():
        assert len(values) == len(__import__("app.locales", fromlist=["CODES"]).CODES) and all(
            values
        )
        expected = set(re.findall(r"\{\w+\}", values[0]))
        assert all(set(re.findall(r"\{\w+\}", value)) == expected for value in values)
    source = (
        Path("app/static/i18n.js")
        .read_text()
        .split("export const messages = ", 1)[1]
        .split(";\nexport const locales", 1)[0]
    )
    assert json.loads(source) == {key: list(values) for key, values in MESSAGES.items()}
