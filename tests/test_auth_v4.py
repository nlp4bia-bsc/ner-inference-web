"""Real account/session flows and adversarial authorization, without auth bypasses."""

import io
import json
import secrets
import time
import zipfile
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.auth.i18n import ROWS
from app.auth.passwords import hash_password, verify_password
from app.errors import ServiceError
from app.main import create_app
from app.services.pipeline import process_job
from app.users.schemas import Register
from scripts.create_admin import create_admin
from tests.auth_helpers import PASSWORD, authenticate, csrf_from
from tests.test_incremental import Predictor, controlled_stats


@pytest.fixture
def auth_app(settings):
    app = create_app(settings)
    app.state.registry.models["es-disease"]["available"] = True
    return app


def public_post(client, path, values):
    prefix = client.app.state.settings.app_prefix
    csrf = csrf_from(client.get(prefix + "/login"))
    return client.post(
        prefix + path, json={**values, "csrf_token": csrf}, headers={"X-CSRF-Token": csrf}
    )


def register_values(email="researcher_a@example.test"):
    return {
        "full_name": "Synthetic Researcher",
        "email": email,
        "institution": "Synthetic University",
        "professional_role": "RESEARCHER",
        "password": PASSWORD,
        "password_confirmation": PASSWORD,
        "legal_accepted": True,
    }


def job(client, count=1, zipped=False):
    data = {"language": "es", "entities": "DISEASE"}
    if zipped:
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, "w", zipfile.ZIP_STORED) as archive:
            for i in range(count):
                archive.writestr(f"folder/{i}.txt", "abc")
        files = {"files": ("corpus.zip", blob.getvalue(), "application/zip")}
    else:
        files = [("files", (f"{i}.txt", b"abc")) for i in range(count)]
    return client.post(client.app.state.settings.app_prefix + "/api/jobs", data=data, files=files)


def complete(app, accepted):
    claimed = app.state.db.claim()
    summary = process_job(
        claimed,
        app.state.settings,
        Predictor(),
        controlled_stats,
        registry_factory=lambda _: app.state.registry,
    )
    app.state.db.finish(claimed["id"], summary)


def private_paths(identity, document="0" * 32):
    return [
        f"/jobs/{identity}",
        f"/jobs/{identity}/viewer",
        f"/api/jobs/{identity}/viewer",
        f"/api/jobs/{identity}",
        f"/api/jobs/{identity}/progress",
        f"/api/jobs/{identity}/documents",
        f"/api/jobs/{identity}/documents/{document}",
        f"/api/jobs/{identity}/documents/{document}/annotations",
        f"/api/jobs/{identity}/documents/{document}/statistics",
        f"/api/jobs/{identity}/documents/{document}/search?q=abc",
        f"/api/jobs/{identity}/documents/{document}/download/txt",
        f"/api/jobs/{identity}/documents/{document}/download/ann",
        f"/api/jobs/{identity}/download/brat",
        f"/api/jobs/{identity}/download/tsv",
        f"/api/jobs/{identity}/statistics",
    ]


def test_registration_verification_argon2_and_no_unverified_processing(auth_app):
    with TestClient(auth_app) as client:
        assert client.get("/", follow_redirects=False).status_code == 303
        authenticate(client, verify=False)
        profile = client.get("/api/profile").json()
        assert (
            profile["system_role"] == "USER"
            and profile["access_tier"] == "STANDARD"
            and profile["max_documents_per_job"] == 100
        )
        assert profile["email_verified_at"] is None
        assert job(client).status_code == 403
        assert client.get("/annotate").status_code == 403
        auth_app.state.mailer.flush()
        raw = parse_qs(urlsplit(auth_app.state.mailer.outbox[-1]["body"].splitlines()[-1]).query)[
            "token"
        ][0]
        assert public_post(client, "/api/auth/verify-email", {"token": raw}).status_code == 200
        assert public_post(client, "/api/auth/verify-email", {"token": raw}).status_code == 422
        client.headers["X-CSRF-Token"] = client.get("/api/auth/session").json()["csrf_token"]
        assert job(client).status_code == 202
        with auth_app.state.db.connect() as c:
            row = c.execute("SELECT * FROM users").fetchone()
        assert row["password_hash"].startswith("$argon2id$") and row["password_hash"] != PASSWORD
        assert verify_password(row["password_hash"], PASSWORD)
        assert hash_password(PASSWORD) != hash_password(PASSWORD)
        assert "password_hash" not in profile and "password" not in profile


@pytest.mark.parametrize("prefix", ["", "/ner"])
def test_every_private_route_is_denied_without_session(settings, prefix):
    app = create_app(
        settings.model_copy(
            update={"app_prefix": prefix, "public_base_url": "http://testserver" + prefix}
        )
    )
    with TestClient(app) as client:
        for path in [
            "/",
            "/dashboard",
            "/annotate",
            "/profile",
            "/admin",
            "/docs",
            "/openapi.json",
            "/api/profile",
            "/api/auth/session",
            "/api/my/jobs",
            "/api/models",
            "/api/languages",
            "/api/admin/users",
            "/api/admin/audit",
            "/api/admin/metrics",
            *private_paths(secrets.token_urlsafe(32)),
        ]:
            response = client.get(prefix + path, follow_redirects=False)
            assert response.status_code == (
                401 if path.startswith("/api/") or path == "/openapi.json" else 303
            ), (path, response.text)
            assert "Synthetic University" not in response.text
        assert client.post(prefix + "/api/jobs").status_code == 401
        assert client.get(prefix + "/static/viewer.js", follow_redirects=False).status_code == 303
        assert client.get(prefix + "/health").json() == {"status": "ok"}
        assert "models_available" not in client.get(prefix + "/ready").json()


def test_two_real_users_and_admin_never_read_each_others_jobs(auth_app):
    with ExitStack() as stack:
        a = stack.enter_context(TestClient(auth_app, client=("10.1.1.1", 1)))
        b = stack.enter_context(TestClient(auth_app, client=("10.1.1.2", 1)))
        authenticate(a, "researcher_a@example.test")
        authenticate(b, "researcher_b@example.test")
        with auth_app.state.db.connect() as c:
            hashes = [r[0] for r in c.execute("SELECT password_hash FROM users")]
            assert len(hashes) == 2 and len(set(hashes)) == 2
        for owner, other in [(a, b), (b, a)]:
            accepted = job(owner).json()
            assert owner.get("/api/jobs/" + accepted["token"] + "/progress").status_code == 200
            assert other.get("/api/jobs/" + accepted["token"] + "/progress").status_code == 404
            complete(auth_app, accepted)
            document = owner.get("/api/jobs/" + accepted["token"] + "/documents").json()["items"][
                0
            ]["document_id"]
            for identifier in [accepted["token"], accepted["job_id"]]:
                for path in private_paths(identifier, document):
                    good = owner.get(path)
                    bad = other.get(path)
                    assert good.status_code == 200, (path, good.text)
                    assert bad.status_code == 404, (path, bad.text)
                    assert "abc" not in bad.text
            assert accepted["job_id"] not in other.get("/api/my/jobs").text
            assert accepted["job_id"] not in other.get("/").text
        # A session-level ADMIN role still cannot bypass job ownership.
        with auth_app.state.db.connect() as c:
            c.execute(
                "UPDATE users SET system_role='ADMIN' WHERE email=?", ("researcher_b@example.test",)
            )
        assert b.get("/api/jobs/" + a.get("/api/my/jobs").json()[0]["id"]).status_code == 404


def test_mass_assignment_profile_and_owner_forgery(auth_app):
    with TestClient(auth_app) as client:
        values = register_values()
        for extra in [
            {"system_role": "ADMIN"},
            {"access_tier": "UNLIMITED"},
            {"owner_user_id": "other"},
        ]:
            assert public_post(client, "/api/auth/register", {**values, **extra}).status_code == 422
        authenticate(client, "researcher_a@example.test")
        profile = client.get("/api/profile").json()
        for key, value in [
            ("system_role", "ADMIN"),
            ("access_tier", "UNLIMITED"),
            ("owner_user_id", "other"),
        ]:
            response = client.patch(
                "/api/profile",
                json={
                    **{
                        k: profile[k]
                        for k in [
                            "full_name",
                            "institution",
                            "professional_role",
                            "professional_role_other",
                            "preferred_locale",
                        ]
                    },
                    key: value,
                },
            )
            assert response.status_code == 422
        assert client.get("/api/admin/users").status_code == 403
        assert (
            client.patch(
                "/api/admin/users/" + profile["id"], json={"system_role": "ADMIN"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/jobs",
                data={"language": "es", "entities": "DISEASE", "owner_user_id": profile["id"]},
                files={"files": ("a.txt", b"abc")},
            ).status_code
            == 422
        )
        assert client.get("/api/profile").json()["access_tier"] == "STANDARD"


def test_csrf_fixation_rotation_and_server_revocation(auth_app):
    with TestClient(auth_app) as client:
        client.cookies.set(
            auth_app.state.settings.session_cookie, "a" * 43, domain="testserver.local", path="/"
        )
        authenticate(client)
        cookie_name = auth_app.state.settings.session_cookie
        raw = client.cookies.get(cookie_name)
        assert raw != "a" * 43
        csrf = client.headers.pop("X-CSRF-Token")
        assert client.post("/api/auth/logout", json={}).status_code == 403
        client.headers["X-CSRF-Token"] = csrf
        assert (
            client.post(
                "/api/auth/logout", json={}, headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert client.post("/api/auth/rotate-session", json={}).status_code == 200
        rotated = client.cookies.get(cookie_name)
        assert rotated != raw and auth_app.state.auth.resolve(raw) is None
        stale = auth_app.state.auth.resolve(rotated)
        assert client.post("/api/auth/logout-all", json={}).status_code == 200
        assert auth_app.state.auth.resolve(rotated) is None
        with pytest.raises(ServiceError):
            auth_app.state.auth.rotate(stale)
        assert client.get("/api/models").status_code == 401
        assert client.get("/", follow_redirects=False).status_code == 303


def test_invalid_expired_revoked_and_suspended_sessions(auth_app):
    with TestClient(auth_app) as client:
        authenticate(client)
        cookie_name = auth_app.state.settings.session_cookie
        raw = client.cookies.get(cookie_name)
        for invalid in ["invented", raw[:-1] + ("A" if raw[-1] != "A" else "B")]:
            assert (
                client.get(
                    "/api/models", headers={"Cookie": cookie_name + "=" + invalid}
                ).status_code
                == 401
            )
        with auth_app.state.db.connect() as c:
            c.execute("UPDATE sessions SET expires_at=?", (time.time() - 1,))
        assert client.get("/api/models").status_code == 401
        authenticate(client, register=False)
        with auth_app.state.db.connect() as c:
            c.execute(
                "UPDATE sessions SET last_seen_at=?",
                (time.time() - auth_app.state.settings.session_idle_seconds - 1,),
            )
        assert client.get("/api/models").status_code == 401
        authenticate(client, register=False)
        with auth_app.state.db.connect() as c:
            c.execute("UPDATE users SET account_status='SUSPENDED'")
        assert client.get("/api/models").status_code == 401


def test_forgot_reset_change_password_tokens_and_generic_responses(auth_app):
    with TestClient(auth_app) as client:
        authenticate(client)
        known = public_post(client, "/api/auth/forgot-password", {"email": "user@example.org"})
        unknown = public_post(client, "/api/auth/forgot-password", {"email": "unknown@example.org"})
        assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
        auth_app.state.mailer.flush()
        raw = parse_qs(urlsplit(auth_app.state.mailer.outbox[-1]["body"].splitlines()[-1]).query)[
            "token"
        ][0]
        replacement = "abcd"
        values = {"token": raw, "password": replacement, "password_confirmation": replacement}
        assert public_post(client, "/api/auth/reset-password", values).status_code == 200
        assert client.get("/api/models").status_code == 401
        assert public_post(client, "/api/auth/reset-password", values).status_code == 422
        assert (
            public_post(
                client, "/api/auth/login", {"email": "user@example.org", "password": PASSWORD}
            ).status_code
            == 401
        )
        assert (
            public_post(
                client, "/api/auth/login", {"email": "user@example.org", "password": replacement}
            ).status_code
            == 200
        )
        client.headers["X-CSRF-Token"] = client.get("/api/auth/session").json()["csrf_token"]
        assert (
            client.post(
                "/api/auth/change-password",
                json={
                    "current_password": replacement,
                    "password": PASSWORD,
                    "password_confirmation": PASSWORD,
                },
            ).status_code
            == 200
        )
        assert client.get("/api/models").status_code == 401
        assert (
            public_post(
                client, "/api/auth/login", {"email": "user@example.org", "password": PASSWORD}
            ).status_code
            == 200
        )
        with patch(
            "app.auth.service.hash_password", side_effect=AssertionError("Hashed before validation")
        ):
            assert (
                public_post(
                    client, "/api/auth/reset-password", {**values, "token": "x" * 43}
                ).status_code
                == 422
            )


@pytest.mark.parametrize(
    "tier,count,accepted,zipped",
    [
        ("STANDARD", 100, True, False),
        ("STANDARD", 101, False, False),
        ("STANDARD", 101, False, True),
        ("EXTENDED", 1000, True, True),
        ("EXTENDED", 1001, False, True),
        ("EXTENDED", 1001, False, False),
        ("UNLIMITED", 1001, True, True),
        ("UNLIMITED", 1001, True, False),
    ],
)
def test_real_account_document_quotas(auth_app, tier, count, accepted, zipped):
    with TestClient(auth_app) as client:
        identity = authenticate(client)["id"]
        # Fixture sets the tier; a separate test below exercises the actual admin API.
        with auth_app.state.db.connect() as c:
            c.execute("UPDATE users SET access_tier=? WHERE id=?", (tier, identity))
        response = job(client, count, zipped)
        assert response.status_code == (202 if accepted else 422), response.text
        with auth_app.state.db.connect() as c:
            assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == int(accepted)
        if not accepted:
            assert str(100 if tier == "STANDARD" else 1000) in response.json()["detail"]


def test_unlimited_still_respects_technical_limits(auth_app):
    auth_app.state.settings.max_zip_entries = 1000
    with TestClient(auth_app) as client:
        authenticate(client)
        with auth_app.state.db.connect() as c:
            c.execute("UPDATE users SET access_tier='UNLIMITED'")
        assert job(client, 1001, True).status_code == 422


def test_legacy_unowned_job_stays_closed_and_deadline_unchanged(auth_app):
    from tests.conftest import enqueue

    raw = enqueue(auth_app.state.db)
    auth_app.state.db.claim()
    auth_app.state.db.finish("job1", failed=True)
    before = auth_app.state.db.get(raw)
    with TestClient(auth_app) as client:
        authenticate(client)
        assert client.get("/api/jobs/" + raw).status_code == 404
        assert client.get("/api/my/jobs").json() == []
    assert auth_app.state.db.get(raw)["expires_at"] == before["expires_at"]


def test_auth_throttle_i18n_and_safe_configuration(settings):
    app = create_app(settings.model_copy(update={"auth_rate_email_attempts": 2}))
    with TestClient(app) as client:
        for _ in range(2):
            assert (
                public_post(
                    client, "/api/auth/login", {"email": "nobody@example.org", "password": PASSWORD}
                ).status_code
                == 401
            )
        assert (
            public_post(
                client, "/api/auth/login", {"email": "nobody@example.org", "password": PASSWORD}
            ).status_code
            == 429
        )
        for language in ["en", "es", "ca"]:
            for path in ["login", "register", "verify-email", "forgot-password", "reset-password"]:
                response = client.get("/" + path + "?lang=" + language)
                assert response.status_code == 200 and f'lang="{language}"' in response.text
        assert all(len(row) == 3 and all(row) for row in ROWS.values())
    production = {
        "_env_file": None,
        "app_env": "production",
        "cookie_secure": True,
        "mail_backend": "none",
        "public_base_url": "https://testserver",
    }
    for invalid in [
        {"cookie_secure": False},
        {"mail_backend": "memory"},
        {"public_base_url": "http://example.org"},
    ]:
        with pytest.raises(ValueError):
            type(settings)(**{**production, **invalid})
    app = create_app(settings.model_copy(update={"mail_backend": "none"}))
    with TestClient(app) as client:
        assert public_post(client, "/api/auth/register", register_values()).status_code == 503


def test_admin_bootstrap_mfa_permissions_audit_and_recovery(settings):
    identity = create_admin(settings, Register(**register_values("admin@example.org")))
    app = create_app(settings)
    with TestClient(app) as admin:
        # Capture the durable outbox generated by the local bootstrap command.
        app.state.mailer.flush()
        raw = parse_qs(urlsplit(app.state.mailer.outbox[-1]["body"].splitlines()[-1]).query)[
            "token"
        ][0]
        assert public_post(admin, "/api/auth/verify-email", {"token": raw}).status_code == 200
        authenticate(admin, "admin@example.org", register=False)
        assert admin.get("/api/admin/users").status_code == 403
        response = admin.post("/api/auth/mfa/start", json={"current_password": PASSWORD})
        secret = response.json()["secret"]
        confirmed = admin.post("/api/auth/mfa/confirm", json={"otp": pyotp.TOTP(secret).now()})
        codes = confirmed.json()["recovery_codes"]
        assert len(codes) == 8 and admin.get("/api/admin/users").status_code == 401
        assert (
            public_post(
                admin,
                "/api/auth/login",
                {"email": "admin@example.org", "password": PASSWORD, "otp": codes[0]},
            ).status_code
            == 200
        )
        admin.headers["X-CSRF-Token"] = admin.get("/api/auth/session").json()["csrf_token"]
        assert admin.get("/api/admin/users").status_code == 200
        with TestClient(app, client=("10.2.2.2", 2)) as other:
            uid = authenticate(other, "researcher_b@example.test")["id"]
            assert (
                admin.patch(
                    "/api/admin/users/" + uid, json={"access_tier": "UNLIMITED"}
                ).status_code
                == 200
            )
            assert other.get("/api/profile").json()["access_tier"] == "UNLIMITED"
            assert (
                admin.patch(
                    "/api/admin/users/" + uid, json={"account_status": "SUSPENDED"}
                ).status_code
                == 200
            )
            assert other.get("/api/profile").status_code == 401
            assert (
                admin.patch(
                    "/api/admin/users/" + uid, json={"account_status": "ACTIVE"}
                ).status_code
                == 200
            )
            authenticate(other, "researcher_b@example.test", register=False)
            assert (
                admin.post("/api/admin/users/" + uid + "/revoke-sessions", json={}).status_code
                == 200
            )
            assert other.get("/api/profile").status_code == 401
        assert admin.get("/api/admin/audit").json()
        assert "password_hash" not in admin.get("/api/admin/users").text
        assert (
            admin.patch(
                "/api/admin/users/" + identity, json={"account_status": "SUSPENDED"}
            ).status_code
            == 409
        )
        assert admin.post("/api/auth/logout", json={}).status_code == 200
        assert (
            public_post(
                admin,
                "/api/auth/login",
                {"email": "admin@example.org", "password": PASSWORD, "otp": codes[0]},
            ).status_code
            == 401
        )
    # Bootstrap must never elevate a pre-existing account or create a second admin.
    with pytest.raises(ValueError):
        create_admin(settings, Register(**register_values("admin@example.org")))


def test_malformed_credentials_are_rejected_without_server_errors(auth_app):
    with TestClient(auth_app) as client:
        csrf = csrf_from(client.get("/login"))
        assert (
            client.post(
                "/api/auth/login",
                json={"csrf_token": "é", "email": "test@example.org", "password": PASSWORD},
            ).status_code
            == 403
        )
        for values in [
            register_values() | {"password": "\ud800" * 15, "password_confirmation": "\ud800" * 15},
            register_values() | {"full_name": "\ud800"},
        ]:
            body = json.dumps({**values, "csrf_token": csrf})
            assert (
                client.post(
                    "/api/auth/register", content=body, headers={"Content-Type": "application/json"}
                ).status_code
                == 422
            )
        assert public_post(client, "/api/auth/verify-email", {"token": "é" * 43}).status_code == 422
        assert (
            public_post(
                client,
                "/api/auth/login",
                {"email": "test@example.org", "password": PASSWORD, "otp": "é"},
            ).status_code
            == 422
        )


def test_delayed_upload_cannot_survive_session_revocation(auth_app, monkeypatch):
    from app.services.documents import ingest as original

    with TestClient(auth_app) as client:
        authenticate(client)
        stale = auth_app.state.auth.resolve(
            client.cookies.get(auth_app.state.settings.session_cookie)
        )

        def ingest(*args, **kwargs):
            result = original(*args, **kwargs)
            auth_app.state.auth.logout(stale, True)
            return result

        monkeypatch.setattr("app.services.jobs.ingest", ingest)
        assert job(client).status_code == 401
        with auth_app.state.db.connect() as c:
            assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_expired_and_revoked_recovery_tokens_and_secure_cookie_flags(settings):
    app = create_app(
        settings.model_copy(
            update={
                "cookie_secure": True,
                "app_prefix": "/ner",
                "public_base_url": "https://testserver/ner",
            }
        )
    )
    with TestClient(app, base_url="https://testserver") as client:
        authenticate(client)
        profile = client.get("/ner/api/auth/session").json()["user"]
        assert profile["email_verified_at"]
        login = public_post(
            client, "/api/auth/login", {"email": "user@example.org", "password": PASSWORD}
        )
        cookie = next(v for v in login.headers.get_list("set-cookie") if "_session=" in v)
        assert (
            app.state.settings.session_cookie + "=" in cookie
            and "HttpOnly" in cookie
            and "Secure" in cookie
            and "Path=/;" in cookie
            and "SameSite=lax" in cookie
            and "Domain=" not in cookie
        )
        public_post(client, "/api/auth/forgot-password", {"email": "user@example.org"})
        app.state.mailer.flush()
        raw = parse_qs(urlsplit(app.state.mailer.outbox[-1]["body"].splitlines()[-1]).query)[
            "token"
        ][0]
        with app.state.db.connect() as c:
            c.execute("UPDATE password_resets SET expires_at=?", (time.time() - 1,))
        assert (
            public_post(
                client,
                "/api/auth/reset-password",
                {"token": raw, "password": PASSWORD, "password_confirmation": PASSWORD},
            ).status_code
            == 422
        )


def test_null_origin_needs_same_origin_metadata_and_valid_csrf(auth_app):
    with TestClient(auth_app) as client:
        csrf = csrf_from(client.get("/login"))
        values = {"email": "user@example.org", "password": PASSWORD, "csrf_token": csrf}
        for site in [None, "none", "same-site", "cross-site"]:
            headers = {"Origin": "null"}
            if site:
                headers["Sec-Fetch-Site"] = site
            assert client.post("/api/auth/login", json=values, headers=headers).status_code == 403
        # Correct origin metadata alone is never sufficient.
        assert (
            client.post(
                "/api/auth/login",
                json={**values, "csrf_token": "0" * 64},
                headers={"Origin": "null", "Sec-Fetch-Site": "same-origin"},
            ).status_code
            == 403
        )
        authenticate(client)
        assert (
            client.post(
                "/api/jobs",
                data={"language": "es", "entities": "DISEASE"},
                files={"files": ("a.txt", b"abc")},
                headers={"Origin": "null", "Sec-Fetch-Site": "same-origin"},
            ).status_code
            == 202
        )


def test_heartbeat_does_not_extend_idle_and_account_mutations_recheck_session(auth_app):
    with TestClient(auth_app) as client:
        identity = authenticate(client)["id"]
        baseline = time.time() - 100
        with auth_app.state.db.connect() as c:
            c.execute("UPDATE sessions SET last_seen_at=? WHERE revoked_at IS NULL", (baseline,))
        assert client.get("/api/auth/session").status_code == 200
        with auth_app.state.db.connect() as c:
            assert (
                c.execute("SELECT last_seen_at FROM sessions WHERE revoked_at IS NULL").fetchone()[
                    0
                ]
                == baseline
            )
        assert client.post("/api/auth/touch", json={}).status_code == 200
        with auth_app.state.db.connect() as c:
            assert (
                c.execute("SELECT last_seen_at FROM sessions WHERE revoked_at IS NULL").fetchone()[
                    0
                ]
                > baseline
            )
        actor = auth_app.state.auth.resolve(
            client.cookies.get(auth_app.state.settings.session_cookie)
        )
        auth_app.state.auth.logout(actor, True)
        from app.users.schemas import Profile

        with pytest.raises(ServiceError):
            auth_app.state.auth.profile(
                actor,
                Profile(full_name="Changed", institution="Changed", professional_role="RESEARCHER"),
            )
        with auth_app.state.db.connect() as c:
            assert (
                c.execute("SELECT full_name FROM users WHERE id=?", (identity,)).fetchone()[0]
                == "Synthetic Researcher"
            )


def test_anonymous_inventory_is_exhaustively_default_denied(auth_app):
    from app.auth.middleware import AUTH_PAGES, PUBLIC_API
    from scripts.inventory_routes import routes

    with TestClient(auth_app) as client:
        for method, route in routes(auth_app):
            if (
                route in AUTH_PAGES
                or route in PUBLIC_API
                or route in ("/health", "/ready", "/static")
            ):
                continue
            path = (
                route.replace("{token}", "a" * 43)
                .replace("{document_id}", "b" * 32)
                .replace("{identity}", "c" * 32)
                .replace("{format}", "ann")
            )
            response = client.request(method, path, follow_redirects=False)
            assert response.status_code == (
                401 if path.startswith("/api/") or path == "/openapi.json" else 303
            ), (method, path, response.status_code)


def test_all_templates_compile_without_mutating_jinja_control_flow():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader("app/templates"), autoescape=True)
    for path in env.list_templates():
        env.get_template(path)


def test_prefix_redirects_are_relative_and_next_cannot_redirect_accounts(settings):
    app = create_app(
        settings.model_copy(
            update={"app_prefix": "/ner", "public_base_url": "http://testserver/ner"}
        )
    )
    with TestClient(app) as client:
        assert client.get("/ner", follow_redirects=False).headers["location"] == "/ner/login"
        authenticate(client)
        assert client.get("/ner", follow_redirects=False).headers["location"] == "/ner/"
        assert client.get("/ner/api/models/").status_code == 404
        response = client.get("/ner/login?next=https://evil.example")
        assert "evil.example" not in response.text
