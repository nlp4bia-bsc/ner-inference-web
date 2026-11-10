"""Approval and administration exercise real sessions, MFA, CSRF and ownership gates."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.users.schemas import Register
from scripts.create_admin import create_admin
from tests.test_auth_v4 import complete, job, private_paths, public_post, register_values

ADMIN_EMAIL = "approver@example.test"


def sign_in(client, email, password=None, otp=""):
    from tests.auth_helpers import PASSWORD

    response = public_post(
        client, "/api/auth/login", {"email": email, "password": password or PASSWORD, "otp": otp}
    )
    if response.status_code == 200:
        prefix = client.app.state.settings.app_prefix
        client.headers["X-CSRF-Token"] = client.get(prefix + "/api/auth/session").json()[
            "csrf_token"
        ]
    return response


@pytest.fixture(params=["", "/ner"])
def administration(settings, request):
    settings = settings.model_copy(
        update={
            "app_prefix": request.param,
            "public_base_url": "http://testserver" + request.param,
            "require_email_verification": False,
            "mail_backend": "none",
            "rate_limit_seconds": 0.001,
        }
    )
    identity = create_admin(settings, Register(**register_values(ADMIN_EMAIL)))
    app = create_app(settings)
    app.state.registry.models["es-disease"]["available"] = True
    with TestClient(app) as administrator:
        prefix = settings.app_prefix
        assert sign_in(administrator, ADMIN_EMAIL).status_code == 200
        assert administrator.get(prefix + "/api/admin/users").status_code == 403
        secret = administrator.post(
            prefix + "/api/auth/mfa/start", json={"current_password": register_values()["password"]}
        ).json()["secret"]
        codes = administrator.post(
            prefix + "/api/auth/mfa/confirm", json={"otp": pyotp.TOTP(secret).now()}
        ).json()["recovery_codes"]
        assert sign_in(administrator, ADMIN_EMAIL, otp=codes[0]).status_code == 200
        yield app, administrator, prefix, identity


def request_account(client, email, **changes):
    response = public_post(client, "/api/auth/register", {**register_values(email), **changes})
    assert response.status_code == 200, response.text
    with client.app.state.db.connect() as connection:
        return dict(connection.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone())


def approve(administration, client, email, **changes):
    _, administrator, prefix, _ = administration
    row = request_account(client, email, **changes)
    response = administrator.post(
        prefix + "/api/admin/users/" + row["id"] + "/review", json={"decision": "APPROVED"}
    )
    assert response.status_code == 200, response.text
    assert sign_in(client, email).status_code == 200
    return row["id"]


def test_pending_requests_cannot_create_sessions_and_admin_sees_full_profile(administration):
    app, administrator, prefix, _ = administration
    with TestClient(app) as applicant:
        row = request_account(
            applicant,
            "pending@example.test",
            professional_role="OTHER",
            professional_role_other="Clinical reviewer",
            full_name="Pending Researcher",
            institution="Synthetic Institute",
        )
        assert row["approval_status"] == "PENDING"
        assert sign_in(applicant, row["email"]).status_code == 403
        assert applicant.get(prefix + "/api/auth/session").status_code == 401
        assert applicant.post(prefix + "/api/jobs", data={"language": "es"}).status_code == 401
        # Even a stale/forged database session cannot bypass the approval guard.
        with app.state.db.connect() as connection:
            raw = app.state.auth._new_session(connection, row)
        applicant.cookies.set(app.state.settings.session_cookie, raw)
        assert applicant.get(prefix + "/api/profile").status_code == 401
        applicant.cookies.clear()
        page = administrator.get(prefix + "/admin").text
        assert all(
            value in page
            for value in (row["full_name"], row["email"], row["institution"], "Clinical reviewer")
        )
        assert "password_hash" not in page and "mfa_secret" not in page
        listing = administrator.get(prefix + "/api/admin/users?approval=PENDING").json()
        assert [r["id"] for r in listing] == [row["id"]]
        response = administrator.post(
            prefix + "/api/admin/users/" + row["id"] + "/review", json={"decision": "APPROVED"}
        )
        assert response.status_code == 200
        assert sign_in(applicant, row["email"]).status_code == 200
        assert applicant.get(prefix + "/api/profile").json()["approval_status"] == "APPROVED"
        assert (
            administrator.post(
                prefix + "/api/admin/users/" + row["id"] + "/review", json={"decision": "REJECTED"}
            ).status_code
            == 409
        )


def test_decline_csrf_mass_assignment_and_url_guards(administration):
    app, administrator, prefix, _ = administration
    with TestClient(app) as applicant, TestClient(app) as ordinary, TestClient(app) as anonymous:
        rejected = request_account(applicant, "declined@example.test")
        approve(administration, ordinary, "ordinary@example.test")
        path = prefix + "/api/admin/users/" + rejected["id"] + "/review"
        assert ordinary.post(path, json={"decision": "APPROVED"}).status_code == 403
        assert (
            administrator.post(
                path, json={"decision": "APPROVED"}, headers={"X-CSRF-Token": "bad"}
            ).status_code
            == 403
        )
        assert (
            administrator.post(
                path, json={"decision": "APPROVED"}, headers={"Origin": "https://untrusted.example"}
            ).status_code
            == 403
        )
        assert administrator.post(path, json={"decision": "REJECTED"}).status_code == 200
        assert sign_in(applicant, rejected["email"]).status_code == 403
        for suffix in (
            "/admin",
            "/admin/projects",
            "/api/admin/users",
            "/api/admin/projects",
            "/admin%2fprojects",
            "/admin?system_role=ADMIN",
        ):
            result = ordinary.get(prefix + suffix, follow_redirects=False)
            assert result.status_code in (403, 404), (suffix, result.text)
            assert rejected["email"] not in result.text
        assert anonymous.get(prefix + "/api/admin/users").status_code == 401
        assert anonymous.get(prefix + "/admin", follow_redirects=False).status_code == 303
        for fields in (
            {"approval_status": "APPROVED"},
            {"system_role": "ADMIN"},
            {"document_limit": 10000},
        ):
            assert (
                public_post(
                    applicant,
                    "/api/auth/register",
                    {**register_values("injected@example.test"), **fields},
                ).status_code
                == 422
            )
            assert ordinary.patch(prefix + "/api/profile", json=fields).status_code == 422


def test_admin_reads_all_projects_users_remain_isolated_and_deletion_frees_owner_quota(
    administration,
):
    app, administrator, prefix, _ = administration
    with TestClient(app) as owner, TestClient(app) as other:
        owner_id = approve(administration, owner, "owner@example.test")
        approve(administration, other, "other@example.test")
        accepted = job(owner).json()
        complete(app, accepted)
        rows = owner.get(prefix + "/api/jobs/" + accepted["job_id"] + "/documents").json()["items"]
        document = rows[0]["document_id"]
        for locator in (accepted["job_id"], accepted["token"]):
            for path in private_paths(locator, document):
                assert other.get(prefix + path).status_code == 404
                result = administrator.get(prefix + path)
                assert result.status_code == 200, (path, result.text)
        projects = administrator.get(prefix + "/api/admin/projects").json()
        assert (
            projects[0]["id"] == accepted["job_id"]
            and projects[0]["owner_email"] == "owner@example.test"
        )
        assert (
            administrator.get(prefix + "/api/my/documents?job_id=" + accepted["job_id"]).json()[
                "items"
            ][0]["document_id"]
            == document
        )
        assert owner.get(prefix + "/api/my/document-usage").json()["occupied"] == 1
        assert (
            administrator.delete(prefix + "/api/admin/projects/" + accepted["job_id"]).status_code
            == 200
        )
        assert owner.get(prefix + "/api/my/document-usage").json()["occupied"] == 0
        tombstone = app.state.db.get(accepted["job_id"])
        assert tombstone["status"] == "DELETED" and tombstone["owner_user_id"] is None
        assert json.loads(tombstone["payload"]) == {}
        assert not app.state.jobs.storage.job(accepted["job_id"]).exists()
        assert owner.get(prefix + "/api/my/documents").json()["items"][0]["state"] == "DELETED"
        assert any(
            event["action"] == "ADMIN_PROJECT_DELETED" and event["target_user_id"] == owner_id
            for event in administrator.get(prefix + "/api/admin/audit").json()
        )


def test_numeric_quota_increases_decreases_and_zero_do_not_destroy_documents(administration):
    app, administrator, prefix, _ = administration
    with TestClient(app) as owner:
        identity = approve(administration, owner, "quota@example.test")
        path = prefix + "/api/admin/users/" + identity
        assert administrator.patch(path, json={"document_limit": 3}).status_code == 200
        accepted = job(owner, count=2).json()
        assert owner.get(prefix + "/api/my/document-usage").json() == {
            "occupied": 2,
            "limit": 3,
            "remaining": 1,
            "total_uploaded": 2,
        }
        assert administrator.patch(path, json={"document_limit": 1}).status_code == 200
        assert owner.get(prefix + "/api/my/document-usage").json()["remaining"] == 0
        assert job(owner).status_code == 422
        assert (
            owner.get(prefix + "/api/jobs/" + accepted["job_id"] + "/documents").json()["total"]
            == 2
        )
        assert administrator.patch(path, json={"document_limit": 5}).status_code == 200
        assert job(owner).status_code == 202
        assert administrator.patch(path, json={"document_limit": 0}).status_code == 200
        assert owner.get(prefix + "/api/profile").json()["max_documents_per_job"] == 0
        assert job(owner).status_code == 422
        assert administrator.patch(path, json={"document_limit": -1}).status_code == 422
        assert administrator.patch(path, json={"document_limit": None}).status_code == 200
        assert owner.get(prefix + "/api/my/document-usage").json()["limit"] == 100


def test_delete_account_removes_profile_projects_tokens_and_blocks_old_session(administration):
    app, administrator, prefix, _ = administration
    with TestClient(app) as owner:
        identity = approve(administration, owner, "erase@example.test")
        accepted = job(owner).json()
        claimed = app.state.db.claim()
        assert claimed["id"] == accepted["job_id"]
        path = prefix + "/api/admin/users/" + identity
        assert (
            administrator.request(
                "DELETE", path, json={"confirm_email": "wrong@example.test"}
            ).status_code
            == 422
        )
        assert app.state.jobs.storage.job(accepted["job_id"]).exists()
        result = administrator.request("DELETE", path, json={"confirm_email": "erase@example.test"})
        assert result.status_code == 200, result.text
        assert owner.get(prefix + "/api/profile").status_code == 401
        assert sign_in(owner, "erase@example.test").status_code == 401
        # A late worker finish cannot resurrect the erased project.
        app.state.db.finish(
            claimed["id"], {"documents": 1}, claimed_version=claimed["content_version"]
        )
        assert app.state.db.get(claimed["id"])["status"] == "DELETED"
        assert not app.state.jobs.storage.job(claimed["id"]).exists()
        with app.state.db.connect() as connection:
            for table, column in (
                ("users", "id"),
                ("sessions", "user_id"),
                ("password_resets", "user_id"),
                ("email_verifications", "user_id"),
                ("upload_ledger", "owner_user_id"),
            ):
                assert (
                    connection.execute(
                        f"SELECT count(*) FROM {table} WHERE {column}=?", (identity,)
                    ).fetchone()[0]
                    == 0
                )
        replacement = request_account(owner, "erase@example.test")
        assert replacement["id"] != identity and replacement["approval_status"] == "PENDING"
        assert sign_in(owner, "erase@example.test").status_code == 403


def test_delete_failure_stays_blocked_and_is_retryable(administration, monkeypatch):
    app, administrator, prefix, _ = administration
    with TestClient(app) as owner:
        identity = approve(administration, owner, "retry@example.test")
        accepted = job(owner).json()
        erase = app.state.jobs.storage.delete

        def fail(_):
            raise OSError("Synthetic deletion failure")

        monkeypatch.setattr(app.state.jobs.storage, "delete", fail)
        path = prefix + "/api/admin/users/" + identity
        assert (
            administrator.request(
                "DELETE", path, json={"confirm_email": "retry@example.test"}
            ).status_code
            == 503
        )
        assert owner.get(prefix + "/api/profile").status_code == 401
        assert (
            administrator.get(prefix + "/api/admin/users?q=retry").json()[0]["approval_status"]
            == "DELETING"
        )
        assert administrator.patch(path, json={"account_status": "ACTIVE"}).status_code == 409
        monkeypatch.setattr(app.state.jobs.storage, "delete", erase)
        assert (
            administrator.request(
                "DELETE", path, json={"confirm_email": "retry@example.test"}
            ).status_code
            == 200
        )
        assert not app.state.jobs.storage.job(accepted["job_id"]).exists()


def test_last_admin_and_self_deletion_are_protected(administration):
    app, administrator, prefix, identity = administration
    path = prefix + "/api/admin/users/" + identity
    assert (
        administrator.request("DELETE", path, json={"confirm_email": ADMIN_EMAIL}).status_code
        == 409
    )
    assert administrator.patch(path, json={"system_role": "USER"}).status_code == 409
    assert administrator.patch(path, json={"account_status": "SUSPENDED"}).status_code == 409
    assert administrator.get(prefix + "/api/admin/users").status_code == 200


def test_deleting_account_during_upload_prevents_admission(administration):
    app, administrator, prefix, _ = administration
    with TestClient(app) as owner:
        identity = approve(administration, owner, "upload@example.test")
        entered, release = Event(), Event()
        from app.services.documents import ingest

        def delayed(*args, **kwargs):
            result = ingest(*args, **kwargs)
            entered.set()
            assert release.wait(10)
            return result

        with patch("app.services.jobs.ingest", delayed), ThreadPoolExecutor() as executor:
            future = executor.submit(job, owner)
            try:
                assert entered.wait(10)
                result = administrator.request(
                    "DELETE",
                    prefix + "/api/admin/users/" + identity,
                    json={"confirm_email": "upload@example.test"},
                )
                assert result.status_code == 200, result.text
            finally:
                release.set()
            assert future.result(timeout=10).status_code == 401
        with app.state.db.connect() as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM jobs WHERE owner_user_id=?", (identity,)
                ).fetchone()[0]
                == 0
            )
        assert not list((app.state.settings.storage_root / "staging").iterdir())


def test_reducing_quota_during_upload_is_enforced_at_admission(administration):
    app, administrator, prefix, _ = administration
    with TestClient(app) as owner:
        identity = approve(administration, owner, "racing-quota@example.test")
        entered, release = Event(), Event()
        from app.services.documents import ingest

        def delayed(*args, **kwargs):
            result = ingest(*args, **kwargs)
            entered.set()
            assert release.wait(10)
            return result

        with patch("app.services.jobs.ingest", delayed), ThreadPoolExecutor() as executor:
            future = executor.submit(job, owner, 2)
            try:
                assert entered.wait(10)
                assert (
                    administrator.patch(
                        prefix + "/api/admin/users/" + identity, json={"document_limit": 1}
                    ).status_code
                    == 200
                )
            finally:
                release.set()
            assert future.result(timeout=10).status_code == 422
        assert owner.get(prefix + "/api/my/document-usage").json()["occupied"] == 0
        assert not list((app.state.settings.storage_root / "staging").iterdir())


def test_queued_foreign_project_position_and_revocation_before_destructive_write(administration):
    from contextlib import contextmanager

    from app.persistence.job_locks import job_lock

    app, administrator, prefix, admin_id = administration
    with TestClient(app) as owner:
        approve(administration, owner, "revocation@example.test")
        accepted = job(owner).json()
        assert (
            administrator.get(prefix + "/api/jobs/" + accepted["job_id"]).json()["queue_position"]
            == 1
        )
        entered, release = Event(), Event()

        @contextmanager
        def delayed(*args):
            with job_lock(*args):
                entered.set()
                assert release.wait(10)
                yield

        with patch("app.admin.erasure.job_lock", delayed), ThreadPoolExecutor() as executor:
            future = executor.submit(
                administrator.delete, prefix + "/api/admin/projects/" + accepted["job_id"]
            )
            try:
                assert entered.wait(10)
                with app.state.db.connect() as connection:
                    # Simulate a change after request authentication, retaining
                    # the auth version to specifically test live role validation.
                    connection.execute(
                        "UPDATE users SET system_role='USER' WHERE id=?", (admin_id,)
                    )
            finally:
                release.set()
            assert future.result(timeout=10).status_code == 403
        assert app.state.jobs.storage.job(accepted["job_id"]).exists()
        assert app.state.db.get(accepted["job_id"])["status"] == "QUEUED"
        assert owner.get(prefix + "/api/jobs/" + accepted["job_id"]).status_code == 200


def test_email_verification_does_not_approve_a_pending_account(administration):
    from urllib.parse import parse_qs, urlsplit

    from app.auth.email import Mailer

    app, _, prefix, _ = administration
    # Exercise the optional legacy email policy with a private synthetic inbox.
    app.state.auth.s = app.state.auth.s.model_copy(
        update={"require_email_verification": True, "mail_backend": "memory"}
    )
    app.state.auth.mailer = Mailer(app.state.auth.s, app.state.db)
    with TestClient(app) as applicant:
        requested = request_account(applicant, "verify-pending@example.test")
        app.state.auth.mailer.flush()
        link = app.state.auth.mailer.outbox[-1]["body"].splitlines()[-1]
        token = parse_qs(urlsplit(link).query)["token"][0]
        assert public_post(applicant, "/api/auth/verify-email", {"token": token}).status_code == 200
        assert sign_in(applicant, requested["email"]).status_code == 403
        assert applicant.get(prefix + "/api/auth/session").status_code == 401


def test_admin_theme_covers_workspace_and_other_owners_pages(administration):
    import re

    app, administrator, prefix, _ = administration
    with TestClient(app) as owner:
        approve(administration, owner, "theme@example.test")
        accepted = job(owner).json()
        for path in (
            "/",
            "/annotate",
            "/documents",
            "/models",
            "/admin",
            "/admin/projects",
            "/jobs/" + accepted["job_id"],
            "/jobs/" + accepted["job_id"] + "/viewer",
        ):
            response = administrator.get(prefix + path)
            assert response.status_code == 200
            assert "admin-theme" in re.search(r'<body class="([^"]*)"', response.text).group(1)
        ordinary = owner.get(prefix + "/?admin=true&system_role=ADMIN")
        assert "admin-theme" not in re.search(r'<body class="([^"]*)"', ordinary.text).group(1)
        assert prefix + "/admin/projects" not in ordinary.text


def test_profile_markup_is_escaped_and_search_is_parameterized(administration):
    app, administrator, prefix, _ = administration
    with TestClient(app) as applicant:
        request_account(
            applicant,
            "markup@example.test",
            full_name="<script>alert(1)</script>",
            institution="<img src=x onerror=alert(1)>",
        )
        response = administrator.get(prefix + "/admin")
        assert "<script>alert(1)</script>" not in response.text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
        assert (
            administrator.get(prefix + "/api/admin/users", params={"q": "' OR 1=1 --"}).json() == []
        )
