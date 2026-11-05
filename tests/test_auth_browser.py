"""Real Chromium sign-up/email/login/isolation/recovery against temporary FastAPI."""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tests.auth_helpers import PASSWORD
from tests.test_auth_v4 import private_paths

pytestmark = pytest.mark.skipif(
    os.environ.get("BROWSER_TESTS") != "1", reason="Real browser opt-in"
)


@pytest.fixture(params=["", "/ner"])
def auth_server(tmp_path, request):
    prefix = request.param
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}" + prefix
    root = tmp_path / "private"
    env = {
        **os.environ,
        "APP_ENV": "test",
        "COOKIE_SECURE": "false",
        "MAIL_BACKEND": "file",
        "STORAGE_ROOT": str(root),
        "PUBLIC_BASE_URL": base,
        "APP_PREFIX": prefix,
        "MIN_FREE_DISK_MB": "0",
        "RATE_LIMIT_SECONDS": "1",
        "AUTH_RATE_IP_ATTEMPTS": "200",
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
                raise RuntimeError("Synthetic server failed to start")
            yield base, root
        finally:
            process.terminate()
            process.wait(timeout=10)


def mail_link(root, email, kind):
    for _ in range(100):
        files = (
            sorted((root / "test-mail").glob("*.json"), key=lambda p: p.stat().st_mtime)
            if (root / "test-mail").exists()
            else []
        )
        for path in reversed(files):
            value = json.loads(path.read_text())
            if value["to"] == email and kind in value["body"]:
                return value["body"].splitlines()[-1]
        time.sleep(0.1)
    raise AssertionError("Expected captured synthetic email was not delivered")


def login(page, base, email, password=PASSWORD):
    page.goto(base + "/login")
    page.locator("#email").fill(email)
    page.locator("#password").fill(password)
    page.get_by_role("button", name="Sign in", exact=True).click()
    page.wait_for_url(base + "/?lang=en")


def signup(page, base, email):
    page.goto(base + "/register")
    for field, value in {
        "full_name": "Synthetic Researcher " + email.split("@")[0],
        "email": email,
        "institution": "Synthetic University",
        "password": PASSWORD,
        "password_confirmation": PASSWORD,
    }.items():
        page.locator("#" + field).fill(value)
    page.select_option("#professional_role", "RESEARCHER")
    page.locator('[name="legal_accepted"]').check()
    page.get_by_role("button", name="Create account", exact=True).click()
    page.get_by_role("status").wait_for()


def verify(page, root, email):
    page.goto(mail_link(root, email, "/verify-email?"))
    page.get_by_role("button", name="Verify email", exact=True).click()
    page.get_by_role("status").wait_for()


def submit_job(page, base, text):
    page.goto(base + "/annotate")
    page.locator('[data-category="DISEASE"] > summary').click()
    page.locator('input[name="models"][value="es-disease"]').check()
    page.get_by_role("tab", name="Paste text").click()
    page.locator("#pasted-text").fill(text)
    with page.expect_response(
        lambda r: r.url == base + "/api/jobs" and r.status == 202
    ) as accepted:
        page.locator("#submit").click()
    record = accepted.value.json()
    page.get_by_role("button", name="Continue to request").click()
    for _ in range(100):
        status = page.request.get(base + "/api/jobs/" + record["job_id"]).json()
        if status["status"] == "COMPLETED":
            break
        time.sleep(0.1)
    assert status["status"] == "COMPLETED"
    return record


def test_real_signup_verification_two_user_isolation_logout_and_reset(auth_server):
    from playwright.sync_api import sync_playwright

    base, root = auth_server
    prefix = "/ner" if base.endswith("/ner") else ""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
            headless=True,
            args=["--no-sandbox"],
        )
        a = browser.new_context(viewport={"width": 1440, "height": 900})
        b = browser.new_context()
        page = a.new_page()
        other = b.new_page()
        page.goto(base + "/")
        assert page.url == base + "/login"
        if os.environ.get("SCREENSHOT_OUTPUT"):
            directory = Path(os.environ["SCREENSHOT_OUTPUT"])
            directory.mkdir(parents=True, exist_ok=True)
            page.screenshot(
                path=str(directory / ("auth-login" + ("-prefix" if prefix else "") + ".png"))
            )
            page.goto(base + "/register")
            page.screenshot(
                path=str(directory / ("auth-register" + ("-prefix" if prefix else "") + ".png")),
                full_page=True,
            )
        signup(page, base, "researcher_a@example.test")
        login(page, base, "researcher_a@example.test")
        assert page.locator("#quota").text_content() == "100"
        session = page.request.get(base + "/api/auth/session").json()
        response = page.request.post(
            base + "/api/jobs",
            headers={"X-CSRF-Token": session["csrf_token"]},
            multipart={"language": "es", "entities": "DISEASE", "pasted_text": "not yet verified"},
        )
        assert response.status == 403
        verify(page, root, "researcher_a@example.test")
        login(page, base, "researcher_a@example.test")
        page.goto(base + "/login")
        page.locator("#email").fill("researcher_a@example.test")
        page.locator("#password").fill("wrong password")
        page.get_by_role("button", name="Sign in", exact=True).click()
        assert "Invalid credentials" in page.get_by_role("status").text_content()
        login(page, base, "researcher_a@example.test")
        job_a = submit_job(page, base, "SYNTHETIC_PRIVATE_A no clinical data")
        page.goto(base + "/jobs/" + job_a["job_id"] + "/viewer")
        page.wait_for_function(
            "() => document.querySelector('#annotated-text')?.textContent.includes('SYNTHETIC_PRIVATE_A')"
        )
        assert "SYNTHETIC_PRIVATE_A" in page.locator("#annotated-text").text_content()
        document = page.request.get(base + "/api/jobs/" + job_a["job_id"] + "/documents").json()[
            "items"
        ][0]["document_id"]
        signup(other, base, "researcher_b@example.test")
        verify(other, root, "researcher_b@example.test")
        login(other, base, "researcher_b@example.test")
        assert job_a["job_id"] not in other.content()
        for identifier in [job_a["job_id"], job_a["token"]]:
            for path in private_paths(identifier, document):
                response = b.request.get(base + path)
                assert response.status == 404, (path, response.status)
                assert "SYNTHETIC_PRIVATE_A" not in response.text()
        job_b = submit_job(other, base, "SYNTHETIC_PRIVATE_B no clinical data")
        for path in private_paths(job_b["token"]):
            assert a.request.get(base + path).status == 404
        page.goto(base + "/")
        assert job_b["job_id"] not in page.content()
        if os.environ.get("SCREENSHOT_OUTPUT"):
            page.screenshot(
                path=str(directory / ("auth-dashboard" + ("-prefix" if prefix else "") + ".png")),
                full_page=True,
            )
        page.get_by_role("button", name="Sign out", exact=True).click()
        page.wait_for_url(base + "/login?lang=en")
        assert a.request.get(base + "/api/jobs/" + job_a["token"]).status == 401
        page.goto(base + "/")
        assert page.url == base + "/login"
        page.get_by_role("link", name="Forgot password", exact=True).click()
        page.locator("#email").fill("researcher_a@example.test")
        page.get_by_role("button", name="Forgot password", exact=True).click()
        page.get_by_role("status").wait_for()
        reset_url = mail_link(root, "researcher_a@example.test", "/reset-password?")
        page.goto(reset_url)
        new_password = PASSWORD + " reset"
        page.locator("#password").fill(new_password)
        page.locator("#password_confirmation").fill(new_password)
        page.get_by_role("button", name="Reset password", exact=True).click()
        assert "Password updated" in page.get_by_role("status").text_content()
        login(page, base, "researcher_a@example.test", new_password)
        assert a.request.get(base + "/api/jobs/" + job_a["job_id"]).status == 200
        with sqlite3.connect(root / "jobs.sqlite3") as c:
            hashes = [r[0] for r in c.execute("SELECT password_hash FROM users")]
            assert len(hashes) == 2 and all(value.startswith("$argon2id$") for value in hashes)
            assert (
                c.execute("SELECT count(*) FROM sessions WHERE revoked_at IS NOT NULL").fetchone()[
                    0
                ]
                >= 2
            )
        # Revocation from another session clears an already loaded terminal viewer.
        page.goto(base + "/jobs/" + job_a["job_id"] + "/viewer")
        page.wait_for_function(
            "() => document.querySelector('#annotated-text')?.textContent.includes('SYNTHETIC_PRIVATE_A')"
        )
        with sqlite3.connect(root / "jobs.sqlite3") as c:
            c.execute(
                "UPDATE sessions SET revoked_at=? WHERE user_id=(SELECT id FROM users WHERE email=?)",
                (time.time(), "researcher_a@example.test"),
            )
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        page.wait_for_url(base + "/login")
        assert "SYNTHETIC_PRIVATE_A" not in page.content()
        # A valid login as a different account must clear an older account's DOM too.
        login(page, base, "researcher_a@example.test", new_password)
        page.goto(base + "/jobs/" + job_a["job_id"] + "/viewer")
        page.wait_for_function(
            "() => document.querySelector('#annotated-text')?.textContent.includes('SYNTHETIC_PRIVATE_A')"
        )
        switched = a.new_page()
        login(switched, base, "researcher_b@example.test")
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        page.wait_for_url(base + "/login")
        assert "SYNTHETIC_PRIVATE_A" not in page.content()
        assert a.request.get(base + "/api/jobs/" + job_a["job_id"]).status == 404
        anon = browser.new_context()
        for path in [
            "/api/models",
            "/api/profile",
            "/openapi.json",
            "/api/jobs/" + job_a["token"] + "/progress",
        ]:
            assert anon.request.get(base + path).status == 401
        anon.close()
        a.close()
        b.close()
        browser.close()


@pytest.mark.parametrize(
    "language,button", [("en", "Create account"), ("es", "Crear cuenta"), ("ca", "Crea un compte")]
)
def test_auth_language_selector_and_registration_choices(auth_server, language, button):
    from playwright.sync_api import sync_playwright

    base, _ = auth_server
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
            headless=True,
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 375, "height": 812})
        page.goto(base + "/register")
        page.select_option("#auth-locale", language)
        page.wait_for_url("**lang=" + language)
        assert page.get_by_role("button", name=button, exact=True).is_visible()
        assert page.locator("#professional_role option").count() == 6
        page.select_option("#professional_role", "OTHER")
        assert page.locator("#professional_role_other").is_visible()
        assert page.locator("#professional_role_other").get_attribute("required") is not None
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        browser.close()


def test_admin_mfa_recovery_display_and_account_management(auth_server):
    import pyotp
    from playwright.sync_api import sync_playwright

    from app.config import Settings
    from app.users.schemas import Register
    from scripts.create_admin import create_admin

    base, root = auth_server
    settings = Settings(
        _env_file=None,
        storage_root=root,
        app_env="test",
        cookie_secure=False,
        mail_backend="memory",
        app_prefix="/ner" if base.endswith("/ner") else "",
        public_base_url=base,
    )
    create_admin(
        settings,
        Register(
            full_name="Synthetic Administrator",
            email="admin@example.test",
            institution="Synthetic University",
            professional_role="RESEARCHER",
            password=PASSWORD,
            password_confirmation=PASSWORD,
            legal_accepted=True,
        ),
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
            headless=True,
            args=["--no-sandbox"],
        )
        context = browser.new_context()
        page = context.new_page()
        verify(page, root, "admin@example.test")
        login(page, base, "admin@example.test")
        assert context.request.get(base + "/api/admin/users").status == 403
        page.goto(base + "/mfa")
        page.locator("#current_password").fill(PASSWORD)
        page.get_by_role("button", name="Set up authenticator").click()
        secret = page.locator("#mfa-secret").text_content()
        page.locator("#otp").fill(pyotp.TOTP(secret).at(time.time() + 30))
        page.get_by_role("button", name="Confirm authenticator code").click()
        page.locator("#recovery-codes").wait_for()
        page.wait_for_timeout(250)
        codes = page.locator("#recovery-codes li").all_text_contents()
        assert len(codes) == 8
        assert context.request.get(base + "/api/admin/users").status == 401
        page.goto(base + "/login")
        page.locator("#email").fill("admin@example.test")
        page.locator("#password").fill(PASSWORD)
        page.locator("#otp").fill(codes[0])
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_url(base + "/?lang=en")
        user_context = browser.new_context()
        other = user_context.new_page()
        signup(other, base, "managed@example.test")
        verify(other, root, "managed@example.test")
        login(other, base, "managed@example.test")
        page.goto(base + "/admin")
        row = page.locator("tbody tr").filter(has_text="managed@example.test")
        row.locator("select[name=access_tier]").select_option("UNLIMITED")
        row.get_by_role("button", name="Save changes", exact=True).click()
        assert user_context.request.get(base + "/api/profile").json()["access_tier"] == "UNLIMITED"
        row = page.locator("tbody tr").filter(has_text="managed@example.test")
        row.locator("select[name=account_status]").select_option("SUSPENDED")
        row.get_by_role("button", name="Save changes", exact=True).click()
        assert user_context.request.get(base + "/api/profile").status == 401
        assert context.request.get(base + "/api/admin/audit").json()
        user_context.close()
        context.close()
        browser.close()
