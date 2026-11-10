"""Default registration has no mail dependency and never claims email possession."""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.auth.passwords import verify_password
from app.config import Settings
from app.main import create_app
from tests.auth_helpers import approve_fixture_account, approve_fixture_database, csrf_from
from tests.test_auth_v4 import public_post, register_values


@pytest.mark.parametrize("prefix", ["", "/ner"])
def test_production_registration_without_mail_and_duplicate_email(tmp_path, prefix):
    settings = Settings(
        _env_file=None,
        storage_root=tmp_path,
        public_base_url="https://testserver" + prefix,
        app_prefix=prefix,
        min_free_disk_mb=0,
    )
    assert not settings.require_email_verification and settings.mail_backend == "none"
    app = create_app(settings)
    app.state.registry.models["es-disease"]["available"] = True
    values = {
        **register_values("Simple@example.org"),
        "password": "abcd",
        "password_confirmation": "abcd",
    }
    with TestClient(app, base_url="https://testserver") as client:
        assert (
            public_post(
                client,
                "/api/auth/register",
                {**values, "password": "abc", "password_confirmation": "abc"},
            ).status_code
            == 422
        )
        created = public_post(client, "/api/auth/register", values)
        assert created.status_code == 200 and created.json()["redirect"] == prefix + "/login"
        duplicate = public_post(
            client,
            "/api/auth/register",
            {
                **values,
                "email": "SIMPLE@EXAMPLE.ORG",
                "password": "wxyz",
                "password_confirmation": "wxyz",
            },
        )
        assert duplicate.status_code == 409 and "already registered" in duplicate.json()["detail"]
        with app.state.db.connect() as c:
            rows = c.execute("SELECT * FROM users").fetchall()
            assert len(rows) == 1 and rows[0]["email_verified_at"] is None
            assert verify_password(rows[0]["password_hash"], "abcd")
            assert c.execute("SELECT count(*) FROM mail_outbox").fetchone()[0] == 0
            assert c.execute("SELECT count(*) FROM email_verifications").fetchone()[0] == 0
        login = public_post(
            client, "/api/auth/login", {"email": "simple@example.org", "password": "abcd"}
        )
        assert login.status_code == 403 and "approval" in login.json()["detail"]
        approve_fixture_account(app, "simple@example.org")
        login = public_post(
            client, "/api/auth/login", {"email": "simple@example.org", "password": "abcd"}
        )
        assert login.status_code == 200
        csrf = client.get(prefix + "/api/auth/session").json()["csrf_token"]
        assert client.get(prefix + "/annotate").status_code == 200
        assert client.get(prefix + "/api/profile").json()["email_verified_at"] is None
        for path in ["/", "/my-jobs"]:
            dashboard = client.get(prefix + path)
            assert dashboard.status_code == 200
            assert "/resend-verification" not in dashboard.text
        assert client.get(prefix + "/api/admin/users").status_code == 403
        admitted = client.post(
            prefix + "/api/jobs",
            data={"language": "es", "entities": "DISEASE"},
            files={"files": ("synthetic.txt", b"Synthetic text.")},
            headers={"X-CSRF-Token": csrf},
        )
        assert admitted.status_code == 202, admitted.text
        changed = client.post(
            prefix + "/api/auth/change-password",
            json={"current_password": "abcd", "password": "wxyz", "password_confirmation": "wxyz"},
            headers={"X-CSRF-Token": csrf},
        )
        assert (
            changed.status_code == 200
            and client.get(prefix + "/api/auth/session").status_code == 401
        )
        assert (
            public_post(
                client, "/api/auth/login", {"email": "simple@example.org", "password": "abcd"}
            ).status_code
            == 401
        )
        assert (
            public_post(
                client, "/api/auth/login", {"email": "simple@example.org", "password": "wxyz"}
            ).status_code
            == 200
        )


def test_concurrent_same_email_creates_only_one_account(tmp_path):
    app = create_app(Settings(_env_file=None, storage_root=tmp_path))
    barrier = Barrier(2)

    def register(email):
        with TestClient(app, base_url="https://testserver") as client:
            csrf = csrf_from(client.get("/register"))
            barrier.wait(timeout=10)
            return client.post(
                "/api/auth/register",
                json={
                    **register_values(email),
                    "password": "abcd",
                    "password_confirmation": "abcd",
                    "csrf_token": csrf,
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(register, ["race@example.org", "RACE@EXAMPLE.ORG"]))
    assert sorted(results) == [200, 409]
    with app.state.db.connect() as c:
        assert c.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_administrator_bootstrap_needs_mfa_but_not_email(tmp_path):
    import pyotp

    from app.users.schemas import Register
    from scripts.create_admin import create_admin

    settings = Settings(_env_file=None, storage_root=tmp_path)
    values = {
        **register_values("admin@example.org"),
        "password": "abcd",
        "password_confirmation": "abcd",
    }
    identity = create_admin(settings, Register(**values))
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver") as client:
        login = {"email": "admin@example.org", "password": "abcd"}
        assert public_post(client, "/api/auth/login", login).status_code == 200
        assert client.get("/api/admin/users").status_code == 403
        csrf = client.get("/api/auth/session").json()["csrf_token"]
        started = client.post(
            "/api/auth/mfa/start", json={"current_password": "abcd"}, headers={"X-CSRF-Token": csrf}
        )
        assert started.status_code == 200
        enrolled = client.post(
            "/api/auth/mfa/confirm",
            json={"otp": pyotp.TOTP(started.json()["secret"]).now()},
            headers={"X-CSRF-Token": csrf},
        )
        assert enrolled.status_code == 200
        assert (
            public_post(
                client, "/api/auth/login", {**login, "otp": enrolled.json()["recovery_codes"][0]}
            ).status_code
            == 200
        )
        assert client.get("/api/admin/users").status_code == 200
        csrf = client.get("/api/auth/session").json()["csrf_token"]
        assert (
            client.patch(
                "/api/admin/users/" + identity,
                json={"access_tier": "EXTENDED"},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 200
        )
        with app.state.db.connect() as c:
            assert (
                c.execute("SELECT email_verified_at FROM users WHERE id=?", (identity,)).fetchone()[
                    0
                ]
                is None
            )
            assert c.execute("SELECT count(*) FROM mail_outbox").fetchone()[0] == 0


@pytest.fixture(params=["", "/ner"])
def simple_server(tmp_path, request):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}" + request.param
    env = {
        **os.environ,
        "APP_ENV": "test",
        "COOKIE_SECURE": "false",
        "MAIL_BACKEND": "none",
        "REQUIRE_EMAIL_VERIFICATION": "false",
        "STORAGE_ROOT": str(tmp_path / "private"),
        "PUBLIC_BASE_URL": base,
        "APP_PREFIX": request.param,
        "MIN_FREE_DISK_MB": "0",
    }
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.auth_browser_server:factory",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + "/health", timeout=0.2)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("Simple registration server did not start")
            yield base
        finally:
            process.terminate()
            process.wait(timeout=10)


@pytest.mark.skipif(os.environ.get("BROWSER_TESTS") != "1", reason="Actual Chromium opt-in")
@pytest.mark.parametrize("width", [390, 1440])
def test_four_character_signup_login_without_verification(simple_server, width, tmp_path):
    from playwright.sync_api import sync_playwright

    base = simple_server
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(base + "/register?lang=es")
        assert page.locator('a[href*="resend-verification"]').count() == 0
        assert page.locator('a[href="mailto:fernando.gallego@bsc.es"]').count() >= 1
        page.locator("#full_name").fill("Synthetic Researcher")
        page.locator("#institution").fill("Synthetic University")
        page.locator("#email").fill("short@example.org")
        page.locator("#password").fill("abc")
        page.locator("#password_confirmation").fill("abc")
        assert not page.locator("#password").evaluate("n=>n.checkValidity()")
        page.locator("#password").fill("😀😀")
        assert not page.locator("#password").evaluate("n=>n.checkValidity()")
        page.locator("#password").fill("abcd")
        page.locator("#password_confirmation").fill("abcd")
        page.locator('[name="legal_accepted"]').check()
        page.locator('button[type="submit"]').click()
        page.wait_for_selector('h1[data-i18n="login"]')
        assert "pendiente de aprobación" in page.get_by_role("status").text_content()
        approve_fixture_database(tmp_path / "private", "short@example.org")
        page.locator("#email").fill("short@example.org")
        page.locator("#password").fill("abcd")
        page.locator('button[type="submit"]').click()
        page.wait_for_url(base + "/?lang=es")
        assert page.locator('a[href*="resend-verification"]').count() == 0
        page.goto(base + "/annotate")
        page.wait_for_selector("#files")
        page.goto(base + "/profile")
        assert (
            "Registered email" in page.locator(".profile-summary").text_content()
            or "Correo registrado" in page.locator(".profile-summary").text_content()
        )
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        browser.close()
