"""Actual administrative navigation, measured aggregates, existing exports and erasure."""

import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from tests.admin_explorer_fixtures import publish_known_results
from tests.test_admin_workflows import administration as administration
from tests.test_admin_workflows import approve
from tests.test_auth_v4 import job

pytestmark = pytest.mark.parametrize("administration", ["", "/annotation-tool"], indirect=True)


def test_real_statistics_and_pagination_do_not_multiply_model_support(administration):
    app, admin, prefix, _ = administration
    with TestClient(app) as owner:
        user_id = approve(administration, owner, "tree@example.test")
        accepted = job(owner, count=2).json()
        rows = publish_known_results(app, accepted)
        root = admin.get(prefix + "/api/admin/explorer/statistics")
        assert root.status_code == 200, root.text
        stats = root.json()["statistics"]
        assert {
            key: stats[key]
            for key in (
                "users",
                "projects",
                "documents",
                "annotations",
                "normalizations",
                "entity_types",
                "models_used",
            )
        } == {
            "users": 2,
            "projects": 1,
            "documents": 2,
            "annotations": 6,
            "normalizations": 2,
            "entity_types": 3,
            "models_used": 3,
        }
        assert stats["annotations_by_model"] == {"A": 2, "B": 4, "C": 2}
        assert stats["documents_by_language"] == {"es": 2}
        assert stats["normalization_methods"] == {"Fuzzy match": 2}
        assert stats["text_statistics"] == {
            "characters": 6,
            "words": 4,
            "tokens": 6,
            "sentences": 2,
        }
        users = admin.get(prefix + "/api/admin/explorer/users?offset=1&limit=1").json()
        assert users["total"] == 2 and len(users["items"]) == 1
        assert "password_hash" not in str(users) and "mfa_secret" not in str(users)
        user = admin.get(prefix + f"/api/admin/explorer/users/{user_id}/projects").json()
        assert user["statistics"]["annotations"] == 6
        project = admin.get(
            prefix + f"/api/admin/explorer/projects/{accepted['job_id']}?limit=1"
        ).json()
        assert project["total"] == 2 and len(project["items"]) == 1
        assert project["statistics"]["documents"] == 2
        assert project["items"][0]["statistics"]["annotations"] == 3
        second = admin.get(
            prefix + f"/api/admin/explorer/projects/{accepted['job_id']}?offset=1&limit=1"
        ).json()
        assert second["items"][0]["document_id"] != project["items"][0]["document_id"]
        assert admin.get(prefix + "/api/admin/explorer/users?limit=101").status_code == 422
        assert admin.get(prefix + "/api/admin/explorer/users?offset=-1").status_code == 422
        assert len(rows) == 2


def test_foreign_document_view_normalization_originals_and_existing_exports(administration):
    app, admin, prefix, _ = administration
    with TestClient(app) as owner, TestClient(app) as other, TestClient(app) as anonymous:
        identity = approve(administration, owner, "owner@example.test")
        approve(administration, other, "other@example.test")
        accepted = job(owner, count=2).json()
        documents = publish_known_results(app, accepted)
        job_id, document = accepted["job_id"], documents[1]["document_id"]
        for path in (
            "/api/admin/explorer/statistics",
            "/api/admin/explorer/users",
            f"/api/admin/explorer/users/{identity}/projects",
            f"/api/admin/explorer/projects/{job_id}",
            "/admin/projects",
            "/admin%2fprojects",
        ):
            assert other.get(prefix + path).status_code == 403
            assert anonymous.get(prefix + path, follow_redirects=False).status_code in (401, 303)
        api = prefix + f"/api/jobs/{job_id}/documents/{document}"
        assert other.get(api).status_code == 404
        assert admin.get(api).json()["text"] == "abc"
        annotations = admin.get(api + "/annotations").json()["items"]
        assert [(r["start"], r["end"]) for r in annotations] == [(0, 2), (1, 3), (0, 1)]
        assert annotations[2]["normalization"]["references"][0]["code_system"] == "UMLS"
        assert admin.get(api + "/download/txt").content == b"abc"
        assert "UMLS:C123" in admin.get(api + "/download/ann").text
        brat = admin.get(prefix + f"/api/jobs/{job_id}/download/brat")
        assert brat.status_code == 200
        with zipfile.ZipFile(io.BytesIO(brat.content)) as archive:
            assert "brat/documents/1.txt" in archive.namelist()
        assert "MEDICATION" in admin.get(prefix + f"/api/jobs/{job_id}/download/tsv").text
        assert (
            admin.get(prefix + f"/api/jobs/{job_id}/statistics").json()["operational"][
                "annotations"
            ]
            == 6
        )
        assert admin.get(prefix + f"/jobs/{job_id}/viewer?document={document}").status_code == 200


def test_document_erasure_refreshes_every_scope_and_frees_owners_quota(administration):
    app, admin, prefix, _ = administration
    with TestClient(app) as owner:
        user_id = approve(administration, owner, "delete@example.test")
        accepted = job(owner, count=2).json()
        docs = publish_known_results(app, accepted)
        job_id, document = accepted["job_id"], docs[0]["document_id"]
        path = prefix + f"/api/jobs/{job_id}/documents/{document}"
        assert admin.delete(path, headers={"X-CSRF-Token": "invalid"}).status_code == 403
        assert admin.delete(path, headers={"Origin": "https://foreign.example"}).status_code == 403
        assert admin.delete(path).status_code == 200
        assert admin.get(path).status_code == 404
        for scope in (
            "/api/admin/explorer/statistics",
            f"/api/admin/explorer/users/{user_id}/projects",
            f"/api/admin/explorer/projects/{job_id}",
        ):
            stats = admin.get(prefix + scope).json()["statistics"]
            assert (
                stats["documents"] == 1
                and stats["annotations"] == 3
                and stats["normalizations"] == 1
            )
            assert stats["entities_by_label"] == {"DISEASE": 1, "SYMPTOM": 1, "MEDICATION": 1}
        usage = owner.get(prefix + "/api/my/document-usage").json()
        assert usage["occupied"] == 1 and usage["total_uploaded"] == 2
        event = next(
            r
            for r in admin.get(prefix + "/api/admin/audit").json()
            if r["action"] == "ADMIN_PROJECT_DOCUMENTS_DELETED"
        )
        assert event["target_user_id"] == user_id and event["details"]["document_ids"] == [document]
        assert not (app.state.jobs.storage.job(job_id) / "input" / docs[0]["filename"]).exists()


def test_expiry_and_deleted_projects_never_contribute_old_counters(administration):
    app, admin, prefix, _ = administration
    with TestClient(app) as owner:
        approve(administration, owner, "expiry@example.test")
        accepted = job(owner, count=2).json()
        docs = publish_known_results(app, accepted)
        # Warm the counter cache, then deny at the retention boundary before cleanup.
        assert (
            admin.get(prefix + "/api/admin/explorer/statistics").json()["statistics"]["annotations"]
            == 6
        )
        with app.state.db.connect() as c:
            c.execute(
                "UPDATE jobs SET expires_at=? WHERE id=?", (time.time() - 1, accepted["job_id"])
            )
        stats = admin.get(prefix + "/api/admin/explorer/statistics").json()["statistics"]
        assert stats["annotations"] == stats["documents"] == stats["normalizations"] == 0
        assert stats["expired_projects"] == 1
        assert (
            admin.get(prefix + f"/api/admin/explorer/projects/{accepted['job_id']}").status_code
            == 410
        )
        assert (
            admin.get(
                prefix
                + f"/api/jobs/{accepted['job_id']}/documents/{docs[0]['document_id']}/annotations"
            ).status_code
            == 410
        )
        assert admin.delete(prefix + f"/api/admin/projects/{accepted['job_id']}").status_code == 200
        stats = admin.get(prefix + "/api/admin/explorer/statistics").json()["statistics"]
        assert stats["annotations"] == stats["expired_projects"] == 0


def test_live_publications_invalidate_only_metadata_cache_and_preserve_partial_results(
    administration,
):
    app, admin, prefix, _ = administration
    with TestClient(app) as owner:
        approve(administration, owner, "live@example.test")
        accepted = job(owner, count=2).json()
        publish_known_results(app, accepted, complete=False, normalized=False)
        scope = prefix + f"/api/admin/explorer/projects/{accepted['job_id']}"
        stats = admin.get(scope).json()["statistics"]
        assert stats["annotations"] == 3 and stats["normalizations"] == 0
        assert stats["partial_projects"] == 1
        # Same mentions/counts, new normalization snapshot: must not reuse old counters.
        publish_known_results(app, accepted, complete=False, normalized=True)
        stats = admin.get(scope).json()["statistics"]
        assert stats["annotations"] == 3 and stats["normalizations"] == 1
        publish_known_results(app, accepted)
        stats = admin.get(scope).json()["statistics"]
        assert (
            stats["annotations"] == 6
            and stats["normalizations"] == 2
            and stats["partial_projects"] == 0
        )


@pytest.mark.parametrize("ownerless", [False, True])
def test_legacy_results_remain_browsable_and_individually_deletable(administration, ownerless):
    import shutil

    app, admin, prefix, _ = administration
    with TestClient(app) as owner:
        approve(administration, owner, "legacy@example.test")
        accepted = job(owner, count=2).json()
        docs = publish_known_results(app, accepted)
        job_id, document = accepted["job_id"], docs[0]["document_id"]
        root = app.state.jobs.storage.job(job_id)
        shutil.rmtree(root / "published")
        with app.state.db.connect() as c:
            c.execute("DELETE FROM documents WHERE job_id=?", (job_id,))
            if ownerless:
                c.execute("UPDATE jobs SET owner_user_id=NULL WHERE id=?", (job_id,))
                c.execute("DELETE FROM upload_ledger WHERE job_id=?", (job_id,))
            else:
                c.execute(
                    "UPDATE upload_ledger SET document_id=lower(hex(randomblob(16))),filename='Historical document' WHERE job_id=?",
                    (job_id,),
                )
        # Read the existing exports through the canonical legacy backfill.
        global_stats = admin.get(prefix + "/api/admin/explorer/statistics").json()["statistics"]
        assert global_stats["annotations"] == 6 and global_stats["normalizations"] == 2
        assert global_stats["text_statistics"]["words"] == 4
        if ownerless:
            users = admin.get(prefix + "/api/admin/explorer/users").json()["items"]
            assert next(row for row in users if row["id"] == "unassigned")["project_count"] == 1
            assert (
                admin.get(prefix + "/api/admin/explorer/users/unassigned/projects").json()["total"]
                == 1
            )
        assert owner.get(prefix + f"/api/jobs/{job_id}/documents").status_code == (
            404 if ownerless else 200
        )
        assert (
            admin.delete(prefix + f"/api/jobs/{job_id}/documents/{document}").json()["deleted"] == 1
        )
        remaining = admin.get(prefix + f"/api/admin/explorer/projects/{job_id}").json()
        assert remaining["total"] == 1 and remaining["statistics"]["annotations"] == 3
        survivor = remaining["items"][0]["document_id"]
        anns = admin.get(prefix + f"/api/jobs/{job_id}/documents/{survivor}/annotations").json()[
            "items"
        ]
        assert anns[2]["normalization"]["code"] == "C123"
        assert len(anns) == 3
        if not ownerless:
            usage = owner.get(prefix + "/api/my/document-usage").json()
            assert usage["occupied"] == 1 and usage["total_uploaded"] == 2
            history = owner.get(prefix + "/api/my/documents").json()["items"]
            assert len(history) == 2 and sum(row["state"] == "DELETED" for row in history) == 1


def test_missing_or_corrupt_publication_is_reported_without_fabricating_counts(administration):
    app, admin, prefix, _ = administration
    with TestClient(app) as owner:
        approve(administration, owner, "damaged@example.test")
        accepted = job(owner, count=2).json()
        docs = publish_known_results(app, accepted)
        root = app.state.jobs.storage.job(accepted["job_id"])
        (root / "published" / docs[0]["document_id"] / "artifact.json").write_text("{")
        stats = admin.get(prefix + "/api/admin/explorer/statistics").json()["statistics"]
        assert stats["annotations"] == 3 and stats["normalizations"] == 1
        assert stats["unavailable_documents"] == stats["partial_projects"] == 1
        assert stats["text_statistics"]["words"] == 2


def test_admin_read_revalidates_after_waiting_for_publication_lock(administration):
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import contextmanager
    from threading import Event
    from unittest.mock import patch

    from app.persistence.job_locks import job_lock

    app, admin, prefix, admin_id = administration
    with TestClient(app) as owner:
        owner_id = approve(administration, owner, "lock@example.test")
        accepted = job(owner, count=2).json()
        publish_known_results(app, accepted)
        # Keep another real approved administrator so self-demotion is permitted.
        assert (
            admin.patch(
                prefix + f"/api/admin/users/{owner_id}", json={"system_role": "ADMIN"}
            ).status_code
            == 200
        )
        entered, release = Event(), Event()

        @contextmanager
        def delayed_lock(settings, identity):
            entered.set()
            assert release.wait(5)
            with job_lock(settings, identity):
                yield

        with patch("app.admin.explorer.job_lock", delayed_lock), ThreadPoolExecutor(1) as pool:
            pending = pool.submit(
                admin.get, prefix + f"/api/admin/explorer/projects/{accepted['job_id']}"
            )
            assert entered.wait(5)
            try:
                assert (
                    admin.patch(
                        prefix + f"/api/admin/users/{admin_id}", json={"system_role": "USER"}
                    ).status_code
                    == 200
                )
            finally:
                release.set()
            response = pending.result(timeout=10)
        assert response.status_code == 401
        assert "Synthetic concept" not in response.text and "DISEASE" not in response.text


@pytest.mark.parametrize("whole_project", [False, True])
def test_global_statistics_recheck_content_deleted_during_aggregation(
    administration, whole_project
):
    from unittest.mock import patch

    from app.admin.explorer import AdminExplorer

    app, admin, prefix, _ = administration
    with TestClient(app) as owner:
        approve(administration, owner, "concurrent-delete@example.test")
        accepted = job(owner, count=2).json()
        docs = publish_known_results(app, accepted)
        original, removed = AdminExplorer.project, False

        def delete_after_snapshot(explorer, identity, *args, **kwargs):
            nonlocal removed
            snapshot = original(explorer, identity, *args, **kwargs)
            if not removed:
                removed = True
                path = prefix + (
                    f"/api/admin/projects/{accepted['job_id']}"
                    if whole_project
                    else f"/api/jobs/{accepted['job_id']}/documents/{docs[0]['document_id']}"
                )
                assert admin.delete(path).status_code == 200
            return snapshot

        with patch.object(AdminExplorer, "project", delete_after_snapshot):
            stats = admin.get(prefix + "/api/admin/explorer/statistics").json()["statistics"]
        assert stats["documents"] == (0 if whole_project else 1)
        assert stats["annotations"] == (0 if whole_project else 3)
        assert stats["normalizations"] == (0 if whole_project else 1)
