"""Validate the generic/Apache split without touching any deployment or volume."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.users.schemas import Register
from scripts.create_admin import create_admin
from tests.test_admin_workflows import sign_in
from tests.test_auth_v4 import register_values


def test_generic_and_apache_profiles_preserve_loopback_data_cpu_and_prefix():
    base = yaml.safe_load(Path("docker-compose.yml").read_text())
    override = yaml.safe_load(Path("docker-compose.apache.yml").read_text())
    assert set(base["services"]) == set(override["services"]) == {"web", "worker"}
    assert base["services"]["web"]["ports"] == ["127.0.0.1:8000:8000"]
    assert set(base["volumes"]) == {"ner-data"}
    assert base["services"]["worker"]["volumes"] == base["services"]["web"]["volumes"]
    assert "ner-data:/data" in base["services"]["web"]["volumes"]
    assert base["services"]["web"]["environment"]["SMTP_STARTTLS"] == "true"
    assert override["services"]["web"]["command"][-2:] == [
        "--proxy-headers",
        "--forwarded-allow-ips=*",
    ]
    assert override["services"]["worker"]["environment"]["DEVICE"] == "cpu"
    assert "APP_PREFIX" not in override["services"]["web"]["environment"]
    assert "numpy==2.3.5\n" in Path("requirements-cpu.lock").read_text()


def test_compose_rendered_apache_defaults_and_private_environment_remain_external():
    if not shutil.which("docker"):
        pytest.skip("Docker Compose unavailable")
    result = subprocess.run(
        ["docker", "compose", "--env-file", "/dev/null", "config", "--format", "json"],
        env={
            **os.environ,
            "COMPOSE_FILE": "docker-compose.yml:docker-compose.apache.yml",
            "APP_PREFIX": "/annotation-tool",
        },
        capture_output=True,
        text=True,
        check=True,
    )
    config = json.loads(result.stdout)
    assert set(config["services"]) == {"web", "worker"}
    for name in ("web", "worker"):
        environment = config["services"][name]["environment"]
        assert environment["APP_ENV"] == "production"
        assert environment["COOKIE_SECURE"] == "true"
        assert environment["APP_PREFIX"] == "/annotation-tool"
        assert environment["PUBLIC_BASE_URL"] == "https://temu.bsc.es/annotation-tool"
        assert environment["ENABLE_MFA"] == "false"
    assert config["services"]["web"]["ports"][0]["host_ip"] == "127.0.0.1"
    assert config["services"]["worker"]["environment"]["DEVICE"] == "cpu"
    assert config["services"]["worker"]["build"]["args"]["NLP_PROFILE"] == "cpu"


def test_production_prefixed_admin_session_works_without_email_or_mfa(tmp_path):
    settings = Settings(
        _env_file=None,
        storage_root=tmp_path,
        app_env="production",
        cookie_secure=True,
        public_base_url="https://temu.bsc.es/annotation-tool",
        app_prefix="/annotation-tool",
        min_free_disk_mb=0,
    )
    create_admin(settings, Register(**register_values("apache@example.test")))
    app = create_app(settings)
    with TestClient(app, base_url="https://temu.bsc.es") as client:
        assert sign_in(client, "apache@example.test").status_code == 200
        for path in (
            "/admin",
            "/admin/projects",
            "/api/admin/explorer/statistics",
            "/api/admin/explorer/users",
        ):
            assert client.get("/annotation-tool" + path).status_code == 200
        cookie = next(
            cookie for cookie in client.cookies.jar if cookie.name == settings.session_cookie
        )
        assert cookie.secure and cookie.path == "/"
        assert client.get("/api/admin/explorer/users").status_code in (401, 404)
