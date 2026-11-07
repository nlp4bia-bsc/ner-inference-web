"""A selection erases precisely the owner's chosen documents, once per project."""

from fastapi.testclient import TestClient

from tests.auth_helpers import AccountClient, authenticate
from tests.test_document_management import application, execute, upload


def documents(client, identity):
    return [
        {"job_id": identity, "document_id": row["document_id"]}
        for row in client.get(f"/api/jobs/{identity}/documents").json()["items"]
    ]


def test_selected_deletion_groups_projects_releases_quota_and_is_idempotent(settings):
    settings.rate_limit_seconds = 0
    app = application(settings)
    with AccountClient(app) as client:
        first = upload(client, 3).json()["job_id"]
        execute(app, settings)
        second = upload(client, 2).json()["job_id"]
        chosen = documents(client, first)[:2] + documents(client, second)[:1]
        response = client.post("/api/my/documents/delete", json={"documents": chosen + chosen[:1]})
        assert response.status_code == 200, response.text
        assert response.json()["deleted"] == 3
        assert response.json()["quota"] == {
            "occupied": 2,
            "remaining": 98,
            "limit": 100,
            "total_uploaded": 5,
        }
        assert app.state.db.get(first)["content_version"] == 1
        assert app.state.db.get(second)["content_version"] == 1
        assert client.get("/api/my/documents?state=DELETED").json()["total"] == 3
        assert (
            client.post("/api/my/documents/delete", json={"documents": chosen}).json()["deleted"]
            == 0
        )
        assert len(documents(client, first)) == len(documents(client, second)) == 1
        execute(app, settings)
        assert app.state.db.get(first)["status"] == "COMPLETED"


def test_selection_requires_csrf_and_preflights_foreign_or_unknown_members(settings):
    settings.rate_limit_seconds = 0
    app = application(settings)
    with AccountClient(app) as owner, TestClient(app) as foreign:
        first = upload(owner, 2).json()["job_id"]
        own = documents(owner, first)
        authenticate(foreign, "foreign-selection@example.org")
        other = upload(foreign, 1).json()["job_id"]
        chosen = own[:1] + documents(foreign, other)
        assert owner.post("/api/my/documents/delete", json={"documents": chosen}).status_code == 404
        assert owner.get("/api/my/document-usage").json()["occupied"] == 2
        assert (
            owner.post(
                "/api/my/documents/delete",
                json={"documents": [own[0], {**own[1], "document_id": "unknown"}]},
            ).status_code
            == 404
        )
        assert owner.post("/api/my/documents/delete", json={"documents": []}).status_code == 422
        proof = owner.headers.pop("X-CSRF-Token")
        assert (
            owner.post("/api/my/documents/delete", json={"documents": own[:1]}).status_code == 403
        )
        owner.headers["X-CSRF-Token"] = proof
        assert owner.get("/api/my/document-usage").json()["occupied"] == 2
        assert foreign.get("/api/my/document-usage").json()["occupied"] == 1
