"""Browser ZIP admission with the documented origin and real CSRF failures."""

import io
import os
import re
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth.i18n import translate
from app.config import Settings
from app.main import create_app
from tests.auth_helpers import authenticate
from tests.test_auth_v4 import register_values
from tests.test_simple_registration import simple_server as simple_server

MODELS = [
    "bsc-bio-ehr-es-distemist",
    "bsc-bio-ehr-es-symptemist",
    "bsc-bio-ehr-es-drugtemist",
    "bsc-bio-ehr-es-proctemist",
    "bsc-bio-ehr-es-livingner-humano",
    "bsc-bio-ehr-es-livingner-species",
    "prof-ner-es",
    "location-tagger",
]


def corpus_zip():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("nested/synthetic-a.txt", "Synthetic research text.\r\n")
        archive.writestr("synthetic-b.txt", "Synthetic second document.\n")
    return output.getvalue()


@pytest.mark.parametrize("prefix", ["", "/ner"])
def test_example_local_origin_admits_zip_with_eight_models(tmp_path, prefix):
    example = Settings(_env_file=Path(".env.example"))
    assert example.public_base_url == "http://127.0.0.1:8000"
    assert example.app_env == "development" and not example.cookie_secure
    app = create_app(
        example.model_copy(
            update={
                "storage_root": tmp_path,
                "app_prefix": prefix,
                "public_base_url": example.public_base_url + prefix,
                "min_free_disk_mb": 0,
            }
        )
    )
    with TestClient(app, base_url=example.public_base_url) as client:
        authenticate(client, verify=False)
        values = {"language": "es", "models": MODELS, "input_mode": "ZIP_ENTRY"}
        headers = {"Origin": example.public_base_url, "Sec-Fetch-Site": "same-origin"}
        token = client.headers.pop("X-CSRF-Token")
        for invalid in [None, "0" * 64]:
            proof = {"X-CSRF-Token": invalid} if invalid else {}
            refused = client.post(
                prefix + "/api/jobs",
                data=values,
                files={"files": ("synthetic.zip", corpus_zip(), "application/zip")},
                headers={**headers, **proof},
            )
            assert refused.status_code == 403
        accepted = client.post(
            prefix + "/api/jobs",
            data=values,
            files={"files": ("synthetic.zip", corpus_zip(), "application/zip")},
            headers={**headers, "X-CSRF-Token": token},
        )
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["url"].startswith(example.public_base_url + prefix + "/jobs/")
        status = client.get(prefix + "/api/jobs/" + accepted.json()["token"]).json()
        assert status["document_count"] == 2 and set(status["models"]) == set(MODELS)


@pytest.mark.parametrize("language", ["en", "es", "ca"])
def test_wrong_service_origin_is_reported_before_upload_admission(settings, caplog, language):
    settings = settings.model_copy(
        update={
            "public_base_url": "https://localhost:8000",
            "model_loading_mode": "on_demand",
            "require_email_verification": False,
        }
    )
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        authenticate(client, verify=False)
        with patch.object(
            app.state.db, "reserve_upload", side_effect=AssertionError("No spooling")
        ):
            response = client.post(
                "/api/jobs?lang=" + language,
                data={"language": "es", "models": MODELS},
                files={"files": ("synthetic.zip", corpus_zip(), "application/zip")},
                headers={"Origin": "http://127.0.0.1:8000", "Sec-Fetch-Site": "same-origin"},
            )
        assert response.status_code == 403
        assert response.json()["detail"] == translate("origin_mismatch", language)
        assert "service address" in translate("origin_mismatch", "en")
        assert "reason=origin_mismatch" in caplog.text
        assert "Synthetic research text" not in caplog.text


@pytest.mark.skipif(os.environ.get("BROWSER_TESTS") != "1", reason="Actual Chromium opt-in")
def test_browser_zip_csrf_failure_preserves_selection_and_can_retry(simple_server):
    from playwright.sync_api import expect, sync_playwright

    base = simple_server
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
            args=["--no-sandbox"],
        )
        page = browser.new_page()

        def csrf(path):
            return re.search(
                r'name="csrf-token" content="([^"]+)"', page.request.get(base + path).text()
            ).group(1)

        assert (
            page.request.post(
                base + "/api/auth/register",
                data={**register_values("zip@example.org"), "csrf_token": csrf("/register")},
            ).status
            == 200
        )
        assert (
            page.request.post(
                base + "/api/auth/login",
                data={
                    "email": "zip@example.org",
                    "password": register_values()["password"],
                    "csrf_token": csrf("/login"),
                },
            ).status
            == 200
        )
        page.goto(base + "/annotate?lang=en")
        page.locator("#tab-zip").click()
        for identity in MODELS:
            check = page.locator(f'input[name="models"][value="{identity}"]')
            check.locator("xpath=ancestor::details").evaluate("node => node.open = true")
            check.check()
        page.locator("#files").set_input_files(
            {"name": "synthetic.zip", "mimeType": "application/zip", "buffer": corpus_zip()}
        )

        def invalidate_proof(route):
            route.continue_(headers={**route.request.headers, "x-csrf-token": "0" * 64})

        page.route("**/api/jobs", invalidate_proof)
        with page.expect_response(lambda response: response.url == base + "/api/jobs") as failed:
            page.locator("#submit").click()
        assert failed.value.status == 403
        expect(page.locator("#error")).to_contain_text("security check failed")
        expect(page.locator("#upload-state")).to_be_hidden()
        expect(page.locator("#submit")).to_be_enabled()
        assert page.locator("#files").evaluate("node => node.files[0].name") == "synthetic.zip"
        assert page.locator('input[name="models"]:checked').count() == 8
        page.unroute("**/api/jobs", invalidate_proof)
        with page.expect_response(lambda response: response.url == base + "/api/jobs") as submitted:
            page.locator("#submit").click()
        assert submitted.value.status == 202
        expect(page.get_by_role("button", name="Continue to request", exact=True)).to_be_visible()
        assert page.request.get(base + "/api/my/jobs").json()[0]["document_count"] == 2
        browser.close()
