"""Loopback aliases keep CSRF proofs, same-origin private links and worker readiness."""

import os
import re
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.auth.origins import trusted_origin
from app.main import create_app
from app.worker import run
from tests.auth_helpers import authenticate
from tests.test_auth_browser import login
from tests.test_auth_v4 import register_values
from tests.test_simple_registration import simple_server as simple_server
from tests.test_submission_security import corpus_zip


@pytest.mark.parametrize(
    "mode,secure,configured,candidate,allowed",
    [
        ("development", False, "http://127.0.0.1:8000", "http://localhost:8000", True),
        ("development", False, "http://localhost:8000", "http://127.0.0.1:8000", True),
        ("development", False, "http://127.0.0.1", "http://LOCALHOST:80", True),
        ("production", True, "https://127.0.0.1:8000", "https://localhost:8000", False),
        ("development", True, "https://127.0.0.1:8000", "https://localhost:8000", False),
        ("development", False, "http://127.0.0.1:8000", "http://localhost:8001", False),
        ("development", False, "http://127.0.0.1:8000", "https://localhost:8000", False),
        ("development", False, "http://127.0.0.1:8000", "http://0.0.0.0:8000", False),
        ("development", False, "http://127.0.0.1:8000", "http://localhost.evil:8000", False),
        ("development", False, "http://127.0.0.1:8000", "http://127.0.0.2:8000", False),
        ("development", False, "http://127.0.0.1:8000", "http://secret@localhost:8000", False),
        ("development", False, "http://127.0.0.1:8000", "http://[invalid", False),
    ],
)
def test_aliases_are_local_and_require_same_scheme_and_port(
    settings, mode, secure, configured, candidate, allowed
):
    settings = settings.model_copy(
        update={"app_env": mode, "cookie_secure": secure, "public_base_url": configured}
    )
    assert trusted_origin(candidate, settings) is allowed


def local_app(settings, configured, prefix):
    return create_app(
        settings.model_copy(
            update={
                "public_base_url": configured + prefix,
                "app_prefix": prefix,
                "model_loading_mode": "on_demand",
                "require_email_verification": False,
            }
        )
    )


@pytest.mark.parametrize("prefix", ["", "/ner"])
@pytest.mark.parametrize(
    "configured,browser", [("127.0.0.1", "localhost"), ("localhost", "127.0.0.1")]
)
def test_both_aliases_admit_zip_with_csrf_and_preserve_browser_link(
    settings, prefix, configured, browser
):
    canonical = f"http://{configured}:8000"
    actual = f"http://{browser}:8000"
    app = local_app(settings, canonical, prefix)
    with TestClient(app, base_url=actual) as client:
        authenticate(client, verify=False)
        proof = client.headers.pop("X-CSRF-Token")
        values = {"language": "es", "models": ["bsc-bio-ehr-es-distemist"]}
        for supplied in [None, "0" * 64]:
            headers = {"Origin": actual, "Sec-Fetch-Site": "same-origin"}
            if supplied:
                headers["X-CSRF-Token"] = supplied
            assert (
                client.post(prefix + "/api/auth/touch", json={}, headers=headers).status_code == 403
            )
            assert (
                client.post(
                    prefix + "/api/jobs",
                    data=values,
                    files={"files": ("synthetic.zip", corpus_zip(), "application/zip")},
                    headers=headers,
                ).status_code
                == 403
            )
        client.headers["X-CSRF-Token"] = proof
        headers = {"Origin": actual, "Sec-Fetch-Site": "same-origin"}
        assert client.post(prefix + "/api/auth/touch", json={}, headers=headers).status_code == 200
        accepted = client.post(
            prefix + "/api/jobs",
            data=values,
            files={"files": ("synthetic.zip", corpus_zip(), "application/zip")},
            headers=headers,
        )
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["url"].startswith(actual + prefix + "/jobs/")
        assert client.get(accepted.json()["url"], follow_redirects=False).status_code == 200


def test_origin_diagnostics_are_safe_and_host_cannot_poison_private_link(settings, caplog):
    app = local_app(settings, "http://127.0.0.1:8000", "")
    with TestClient(app, base_url="http://localhost:8000") as client:
        authenticate(client, verify=False)
        rejected = client.post(
            "/api/auth/touch",
            json={},
            headers={
                "Origin": "http://localhost:8001",
                "Referer": "http://localhost:8001/jobs/PATIENT_SECRET?token=COOKIE_SECRET",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        assert rejected.status_code == 403
        assert "request_origin=http://localhost:8001" in caplog.text
        assert "configured_origin=http://127.0.0.1:8000" in caplog.text
        assert "fetch_site=same-origin" in caplog.text
        assert "PATIENT_SECRET" not in caplog.text and "COOKIE_SECRET" not in caplog.text
        accepted = client.post(
            "/api/jobs",
            data={"language": "es", "models": ["bsc-bio-ehr-es-distemist"]},
            files={"files": ("synthetic.txt", b"Synthetic research text.")},
            headers={"Origin": "http://localhost:8000", "Host": "evil.example"},
        )
        assert accepted.status_code == 202
        assert accepted.json()["url"].startswith("http://127.0.0.1:8000/jobs/")


def test_worker_missing_runtime_exits_before_touching_queue(settings, monkeypatch, caplog):
    database = Mock()
    storage = Mock()
    monkeypatch.setattr("app.worker.Settings", lambda: settings)
    monkeypatch.setattr("app.worker.Database", database)
    monkeypatch.setattr("app.worker.LocalStorage", storage)
    monkeypatch.setattr("app.services.runtime.find_spec", lambda _: None)
    with pytest.raises(SystemExit, match="requirements-cpu.lock"):
        run()
    database.assert_not_called()
    storage.assert_not_called()
    assert "missing_modules=torch,transformers,huggingface_hub,lab" in caplog.text


@pytest.mark.skipif(os.environ.get("BROWSER_TESTS") != "1", reason="Actual Chromium opt-in")
def test_browser_localhost_login_zip_and_private_job_link(simple_server, tmp_path):
    from playwright.sync_api import expect, sync_playwright

    from tests.auth_helpers import approve_fixture_database

    canonical = simple_server
    base = canonical.replace("127.0.0.1", "localhost")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
            args=["--no-sandbox"],
        )
        page = browser.new_page()
        proof = re.search(
            r'name="csrf-token" content="([^"]+)"', page.request.get(base + "/register").text()
        ).group(1)
        assert (
            page.request.post(
                base + "/api/auth/register",
                data={**register_values("aliases@example.org"), "csrf_token": proof},
            ).status
            == 200
        )
        approve_fixture_database(tmp_path / "private", "aliases@example.org")
        login(page, base, "aliases@example.org")
        page.goto(base + "/annotate")
        page.locator("#tab-zip").click()
        page.locator('[data-category="DISEASE"] > summary').click()
        page.locator('input[name="models"][value="bsc-bio-ehr-es-distemist"]').check()
        page.locator("#files").set_input_files(
            {"name": "synthetic.zip", "mimeType": "application/zip", "buffer": corpus_zip()}
        )
        with page.expect_response(lambda response: response.url == base + "/api/jobs") as result:
            page.locator("#submit").click()
        assert result.value.status == 202, result.value.text()
        assert result.value.json()["url"].startswith(base + "/jobs/")
        expect(page.locator(".private-link")).to_have_attribute("href", re.compile(re.escape(base)))
        page.get_by_role("button", name="Continue to request", exact=True).click()
        page.wait_for_url(re.compile(re.escape(base) + r"/jobs/[a-f0-9]+"))
        assert page.request.get(base + "/api/auth/session").status == 200
        assert page.request.get(canonical + "/api/auth/session").status == 401
        browser.close()
