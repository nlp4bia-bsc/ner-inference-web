"""Diagnose shell overrides without exposing credentials or changing precedence."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from scripts.check_config import main
from tests.auth_helpers import authenticate


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("prefix", ["", "/ner"])
def test_workspace_notice_follows_verification_policy(settings, required, prefix):
    settings = settings.model_copy(
        update={
            "require_email_verification": required,
            "app_prefix": prefix,
            "public_base_url": "http://testserver" + prefix,
        }
    )
    app = create_app(settings)
    with TestClient(app) as client:
        authenticate(client, verify=False)
        assert client.get(prefix + "/api/auth/session").json()["user"]["email_verified_at"] is None
        for language in ["en", "es", "ca"]:
            for path in ["/", "/my-jobs"]:
                page = client.get(prefix + path + "?lang=" + language)
                assert page.status_code == 200
                assert ("/resend-verification" in page.text) is required


def test_config_diagnostic_identifies_shell_overrides_without_credentials(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=development\nCOOKIE_SECURE=false\n"
        "PUBLIC_BASE_URL=http://127.0.0.1:8000\nREQUIRE_EMAIL_VERIFICATION=false\n"
        "SMTP_PASSWORD=DO_NOT_PRINT_SMTP\nHF_TOKEN=DO_NOT_PRINT_HUB\n"
    )
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://localhost:8000")
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    monkeypatch.setenv("SMTP_PASSWORD", "DO_NOT_PRINT_SHELL_SECRET")
    assert main(["--expect-origin", "http://127.0.0.1:8000"]) == 1
    output = capsys.readouterr().out
    data = json.loads(output)
    assert data["env_file"] == {"path": str(env_file), "exists": True}
    assert data["settings"]["PUBLIC_BASE_URL"] == {
        "value": "https://localhost:8000",
        "source": "environment",
    }
    assert data["settings"]["REQUIRE_EMAIL_VERIFICATION"] == {
        "value": True,
        "source": "environment",
    }
    assert not data["origin_matches"]
    assert (
        "DO_NOT_PRINT" not in output and "SMTP_PASSWORD" not in output and "HF_TOKEN" not in output
    )
    monkeypatch.delenv("PUBLIC_BASE_URL")
    monkeypatch.delenv("REQUIRE_EMAIL_VERIFICATION")
    assert main(["--expect-origin", "http://127.0.0.1:8000"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["origin_matches"]
    assert data["settings"]["PUBLIC_BASE_URL"]["source"] == ".env"
    assert data["settings"]["REQUIRE_EMAIL_VERIFICATION"]["value"] is False


def test_diagnostic_reports_missing_env_and_inference_libraries(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for name in ["PUBLIC_BASE_URL", "APP_ENV", "COOKIE_SECURE", "REQUIRE_EMAIL_VERIFICATION"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.services.runtime.find_spec", lambda _: None)
    assert main([]) == 0
    data = json.loads(capsys.readouterr().out)
    assert not data["env_file"]["exists"]
    assert data["settings"]["PUBLIC_BASE_URL"] == {
        "value": "https://localhost:8000",
        "source": "default",
    }
    assert data["settings"]["REQUIRE_EMAIL_VERIFICATION"]["value"] is False
    assert not any(data["inference_dependencies"].values())
