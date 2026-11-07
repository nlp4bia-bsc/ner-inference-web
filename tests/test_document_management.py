"""Retained quota/history and irreversible content deletion across worker states."""

import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.persistence.job_locks import JobContentChanged
from app.services.cleanup import cleanup
from app.services.pipeline import process_job
from tests.auth_helpers import AccountClient, authenticate
from tests.test_incremental import Predictor, controlled_stats


def application(settings):
    app = create_app(settings)
    app.state.registry.models["es-disease"]["available"] = True
    return app


def upload(client, count=2):
    return client.post(
        "/api/jobs",
        data={"language": "es", "entities": "DISEASE"},
        files=[("files", (f"doc-{n}.txt", b"abc")) for n in range(count)],
    )


def execute(app, settings, adapter=None):
    claimed = app.state.db.claim()
    summary = process_job(
        claimed,
        settings,
        adapter or Predictor(),
        controlled_stats,
        registry_factory=lambda _: app.state.registry,
    )
    app.state.db.finish(claimed["id"], summary, claimed_version=claimed["content_version"])
    return claimed


def test_delete_completed_doc_repackages_without_rerunning_models_or_extending_expiry(settings):
    app = application(settings)
    with AccountClient(app) as client:
        accepted = upload(client)
        assert accepted.status_code == 202
        identity = accepted.json()["job_id"]
        execute(app, settings)
        original = app.state.db.get(identity)
        root = app.state.jobs.storage.job(identity)
        docs = client.get(f"/api/jobs/{identity}/documents").json()["items"]
        assert client.get("/api/my/document-usage").json() == {
            "occupied": 2,
            "limit": 100,
            "remaining": 98,
            "total_uploaded": 2,
        }
        removed = client.delete(f"/api/jobs/{identity}/documents/{docs[0]['document_id']}")
        assert removed.status_code == 200 and removed.json()["quota"]["occupied"] == 1
        assert not (root / "input" / docs[0]["filename"]).exists()
        assert not (root / "published" / docs[0]["document_id"]).exists()
        assert not (root / "output").exists()
        assert app.state.db.get(identity)["status"] == "QUEUED"

        class NoPrediction:
            def predict(self, *args):
                raise AssertionError("Deletion must reuse existing annotations")

        execute(app, settings, NoPrediction())
        current = app.state.db.get(identity)
        assert current["status"] == "COMPLETED" and current["expires_at"] == original["expires_at"]
        with zipfile.ZipFile(root / "output" / "results.zip") as archive:
            assert not any(docs[0]["filename"] in name for name in archive.namelist())
        manifest = json.loads((root / "output" / "manifest.json").read_text())
        assert manifest["documents"] == [docs[1]["filename"]]
        assert (
            client.get(f"/api/jobs/{identity}/documents/{docs[0]['document_id']}").status_code
            == 404
        )
        history = client.get("/api/my/documents").json()
        assert history["total"] == 2 and {row["state"] for row in history["items"]} == {
            "DELETED",
            "STORED",
        }
        with app.state.db.connect() as connection:
            connection.execute(
                "UPDATE jobs SET expires_at=? WHERE id=?", (time.time() - 1, identity)
            )
        assert client.get("/api/my/document-usage").json()["occupied"] == 0
        cleanup(app.state.db, app.state.jobs.storage)
        with app.state.db.connect() as connection:
            connection.execute(
                "UPDATE jobs SET expired_at=? WHERE id=?", (time.time() - 90000, identity)
            )
        cleanup(app.state.db, app.state.jobs.storage)
        assert client.get("/api/my/documents").json()["total"] == 2
        assert client.get("/api/my/document-usage").json()["total_uploaded"] == 2


def test_quota_counts_all_retained_jobs_and_deletion_frees_a_slot(settings):
    app = application(settings)
    with AccountClient(app) as client:
        accepted = upload(client, 100)
        assert accepted.status_code == 202
        usage = client.get("/api/my/document-usage").json()
        assert usage["occupied"] == 100 and usage["remaining"] == 0
        assert upload(client, 1).status_code == 422
        identity = accepted.json()["job_id"]
        doc = client.get(f"/api/jobs/{identity}/documents").json()["items"][0]
        assert (
            client.delete(f"/api/jobs/{identity}/documents/{doc['document_id']}").status_code == 200
        )
        with app.state.db.connect() as connection:
            connection.execute("UPDATE limits SET accepted_at=0")
        assert upload(client, 1).status_code == 202
        usage = client.get("/api/my/document-usage").json()
        assert usage == {"occupied": 100, "limit": 100, "remaining": 0, "total_uploaded": 101}


@pytest.mark.parametrize("whole_job", [False, True])
def test_deletion_during_prediction_cannot_publish_or_resurrect_deleted_content(
    settings, whole_job
):
    app = application(settings)
    with AccountClient(app) as client:
        accepted = upload(client)
        identity = accepted.json()["job_id"]
        docs = client.get(f"/api/jobs/{identity}/documents").json()["items"]
        claimed = app.state.db.claim()

        class DeletingPredictor(Predictor):
            def predict(self, *args):
                route = f"/api/jobs/{identity}" + (
                    "" if whole_job else "/documents/" + docs[0]["document_id"]
                )
                assert client.delete(route).status_code == 200
                return super().predict(*args)

        with pytest.raises(JobContentChanged):
            process_job(
                claimed,
                settings,
                DeletingPredictor(),
                controlled_stats,
                registry_factory=lambda _: app.state.registry,
            )
        app.state.db.finish(identity, failed=True, claimed_version=claimed["content_version"])
        root = app.state.jobs.storage.job(identity)
        assert not (root / "input" / docs[0]["filename"]).exists()
        assert not (root / "published" / docs[0]["document_id"]).exists()
        assert not (root / "output").exists()
        if whole_job:
            assert app.state.db.get(identity)["status"] == "DELETED"
            cleanup(app.state.db, app.state.jobs.storage)
            app.state.db.finish(identity, failed=True, claimed_version=claimed["content_version"])
            assert app.state.db.get(identity)["status"] == "DELETED"
            assert not root.exists()
        else:
            assert app.state.db.get(identity)["status"] == "QUEUED"
            execute(app, settings)
            assert client.get(f"/api/jobs/{identity}/documents").json()["total"] == 1


def test_deletion_requires_current_owner_and_csrf_and_history_is_private(settings):
    app = application(settings)
    with AccountClient(app) as owner, TestClient(app) as other:
        identity = upload(owner).json()["job_id"]
        authenticate(other, "foreign@example.org")
        assert other.delete(f"/api/jobs/{identity}").status_code == 404
        assert other.get("/api/my/documents").json()["total"] == 0
        proof = owner.headers.pop("X-CSRF-Token")
        assert owner.delete(f"/api/jobs/{identity}").status_code == 403
        owner.headers["X-CSRF-Token"] = proof
        assert owner.delete(f"/api/jobs/{identity}").status_code == 200
        assert owner.delete(f"/api/jobs/{identity}").json()["deleted"] == 0
        assert owner.get("/api/my/document-usage").json()["occupied"] == 0
        assert owner.get("/api/my/documents").json()["total"] == 2


def test_history_filters_before_pagination(settings):
    app = application(settings)
    with AccountClient(app) as client:
        first = upload(client, 60).json()["job_id"]
        records = client.get(f"/api/jobs/{first}/documents?limit=100").json()["items"]
        for row in records[:3]:
            assert (
                client.delete(f"/api/jobs/{first}/documents/{row['document_id']}").status_code
                == 200
            )
        removed = client.get(
            f"/api/my/documents?state=DELETED&job_id={first}&limit=1&offset=1"
        ).json()
        assert removed["total"] == 3 and len(removed["items"]) == 1
        retained = client.get("/api/my/documents?state=STORED&offset=50").json()
        assert retained["total"] == 57 and len(retained["items"]) == 7


def test_two_simultaneous_submissions_cannot_claim_the_same_last_quota_slot(settings):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    settings.rate_limit_seconds = 0
    app = application(settings)
    with AccountClient(app) as client:
        assert upload(client, 99).status_code == 202
        cookies = dict(client.cookies)
        headers = dict(client.headers)
        barrier = Barrier(2)

        def attempt(number):
            with TestClient(app, cookies=cookies, headers=headers) as other:
                barrier.wait()
                return upload(other, 1).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(attempt, range(2)))
        assert sorted(statuses) == [202, 422]
        assert client.get("/api/my/document-usage").json()["occupied"] == 100


def test_bulk_delete_all_projects_is_owner_scoped_and_preserves_upload_history(settings):
    settings.rate_limit_seconds = 0
    app = application(settings)
    with AccountClient(app) as owner, TestClient(app) as foreign:
        identities = [upload(owner, 2).json()["job_id"] for _ in range(2)]
        execute(app, settings)  # Completed content plus a queued project.
        authenticate(foreign, "another-owner@example.org")
        foreign_id = upload(foreign, 1).json()["job_id"]
        proof = owner.headers.pop("X-CSRF-Token")
        assert owner.delete("/api/my/documents").status_code == 403
        owner.headers["X-CSRF-Token"] = proof
        result = owner.delete("/api/my/documents")
        assert result.status_code == 200 and result.json()["deleted"] == 4
        assert result.json()["quota"] == {
            "occupied": 0,
            "remaining": 100,
            "limit": 100,
            "total_uploaded": 4,
        }
        assert owner.get("/api/my/documents").json()["total"] == 4
        assert all(
            row["state"] == "DELETED" for row in owner.get("/api/my/documents").json()["items"]
        )
        for identity in identities:
            assert not app.state.jobs.storage.job(identity).exists()
            assert identity not in owner.get("/?lang=en").text
        assert foreign.get("/api/my/document-usage").json()["occupied"] == 1
        assert app.state.jobs.storage.job(foreign_id).exists()
        assert owner.delete("/api/my/documents").json()["deleted"] == 0
