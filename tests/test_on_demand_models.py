"""Cold Hub cache, real CPU classifier, and isolation of one model's failures."""

import hashlib
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest
import yaml

from app.main import create_app
from app.services.model_cache import ModelCache
from app.services.pipeline import process_job
from app.services.registry import Registry, model_snapshot
from tests.auth_helpers import AccountClient
from tests.test_auth_v4 import register_values
from tests.test_incremental import controlled_stats
from tests.test_simple_registration import simple_server as simple_server


def configured(settings, tmp_path, models=("bad", "good")):
    catalog = {
        "languages": {
            "es": {
                "display_name": "Spanish",
                "entities": {"DISEASE": {"display_name": "Diseases", "models": list(models)}},
            }
        },
        "models": {
            name: {
                "repository": "synthetic/" + name,
                "language": "es",
                "languages": ["es"],
                "target_label": "DISEASE",
                "label_mapping": {"DISEASE": "DISEASE"},
                "enabled": False,
                "schema_review": "pending",
            }
            for name in models
        },
    }
    path = tmp_path / "catalog.yaml"
    path.write_text(yaml.safe_dump(catalog))
    return settings.model_copy(
        update={
            "model_loading_mode": "on_demand",
            "model_config_path": path,
            "model_cache_dir": tmp_path / "hub",
            "device": "cpu",
        }
    )


def test_all_published_configured_models_are_selectable_without_preflight(settings):
    s = settings.model_copy(update={"model_loading_mode": "on_demand"})
    registry = Registry(s)
    published = [model for model in registry.models.values() if model.get("repository")]
    assert len(published) >= 36 and all(model["available"] for model in published)
    for model in published:
        chosen = registry.select(model["languages"][0], [], [model["model_id"]])
        assert chosen and chosen[-1]["model_id"] == model["model_id"]
    assert not s.hub_cache.exists()  # Listing/selecting does not download anything.


@pytest.mark.parametrize("kind", ["exception", "bad-offset", "missing-module"])
def test_failed_model_is_logged_without_patient_text_and_other_results_survive(
    settings, tmp_path, caplog, kind
):
    s = configured(settings, tmp_path)
    app = create_app(s)

    class Predictor:
        def predict(self, model, documents, output, device):
            if model["model_id"] == "bad" and kind == "missing-module":
                raise ModuleNotFoundError(
                    "PATIENT_SECRET must never enter logs", name="huggingface_hub"
                )
            if model["model_id"] == "bad" and kind == "exception":
                raise RuntimeError("PATIENT_SECRET must never enter logs")
            return [
                {
                    "filename": name,
                    "label": "DISEASE",
                    "start_span": 0,
                    "end_span": 6,
                    "text": "PATIENT_SECRET" if model["model_id"] == "bad" else text[:6],
                    "score": 0.8,
                }
                for name, text in documents.items()
            ], {"model_id": model["model_id"]}

    with AccountClient(app) as client:
        accepted = client.post(
            "/api/jobs",
            data={"language": "es", "models": ["bad", "good"]},
            files={"files": ("a.txt", b"Cancer.")},
        )
        assert accepted.status_code == 202, accepted.text
        job = app.state.db.claim()
        summary = process_job(job, s, Predictor(), controlled_stats)
        app.state.db.finish(job["id"], summary)
        status = client.get("/api/jobs/" + accepted.json()["token"]).json()
        assert status["status"] == "COMPLETED_WITH_ERRORS"
        assert summary["failed_models"] == 1 and summary["successful_documents"] == 1
        if kind == "missing-module":
            assert summary["model_errors"][0]["missing_module"] == "huggingface_hub"
            assert "missing_module=huggingface_hub" in caplog.text
        root = app.state.jobs.storage.job(job["id"])
        manifest = json.loads((root / "output" / "manifest.json").read_text())
        assert manifest["partial"] and manifest["model_errors"][0]["model_id"] == "bad"
        tsv = (root / "output" / "annotations.tsv").read_text()
        assert "Cancer" in tsv and "good" in tsv and "bad" not in tsv
        assert "PATIENT_SECRET" not in caplog.text and "model_id=bad" in caplog.text
        assert (root / "model-errors.json").is_file()


def test_no_model_success_never_publishes_fake_results(settings, tmp_path):
    s = configured(settings, tmp_path)
    app = create_app(s)

    class Broken:
        def predict(self, *args):
            raise OSError("No weights")

    with AccountClient(app) as client:
        response = client.post(
            "/api/jobs",
            data={"language": "es", "models": ["bad", "good"]},
            files={"files": ("a.txt", b"Cancer.")},
        )
        job = app.state.db.claim()
        with pytest.raises(ValueError, match="No documents completed"):
            process_job(job, s, Broken(), controlled_stats)
        app.state.db.finish(job["id"], failed=True)
        assert (
            client.get("/api/jobs/" + response.json()["token"] + "/download/brat").status_code
            == 409
        )


@pytest.fixture
def tiny_hub(tmp_path, monkeypatch):
    hub = pytest.importorskip("huggingface_hub")
    from tests.test_real_inference import build_checkpoint

    checkpoint = build_checkpoint(tmp_path)
    import torch
    from transformers import AutoModelForTokenClassification

    weights = AutoModelForTokenClassification.from_pretrained(checkpoint, local_files_only=True)
    weights.config.id2label = {0: "O", 1: "B-ENFERMEDAD", 2: "I-ENFERMEDAD"}
    weights.config.label2id = {label: i for i, label in weights.config.id2label.items()}
    with torch.no_grad():
        weights.classifier.bias[1] = (
            10  # Deterministic synthetic predictions, not a clinical model.
        )
    weights.save_pretrained(checkpoint)
    (
        checkpoint / "encoding.json"
    ).unlink()  # A standard Hub token classifier, not ner_lab's saved format.
    files = {p.name: p.read_bytes() for p in checkpoint.iterdir() if p.is_file()}
    commit = "a" * 40
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_file(self, head=False):
            path = urlsplit(self.path).path
            calls.append((self.command, path))
            if path.startswith(("/api/models/synthetic/bad", "/synthetic/bad/")):
                self.send_error(404)
                return
            if path.startswith("/api/models/") and "/tree/" in path:
                body = json.dumps(
                    [
                        {
                            "type": "file",
                            "oid": hashlib.sha1(data).hexdigest(),
                            "size": len(data),
                            "path": name,
                        }
                        for name, data in files.items()
                    ]
                ).encode()
            elif path.startswith("/api/models/"):
                body = json.dumps(
                    {
                        "id": "synthetic/good",
                        "sha": commit,
                        "private": False,
                        "gated": False,
                        "siblings": [{"rfilename": name} for name in files],
                    }
                ).encode()
            else:
                name = path.rsplit("/", 1)[-1]
                if name not in files:
                    self.send_error(404)
                    return
                body = files[name]
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Content-Type",
                "application/json" if path.startswith("/api/") else "application/octet-stream",
            )
            self.send_header("ETag", '"' + hashlib.sha256(body).hexdigest() + '"')
            self.send_header("X-Repo-Commit", commit)
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def do_GET(self):
            self.handle_file()

        def do_HEAD(self):
            self.handle_file(True)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    real_download = hub.snapshot_download
    monkeypatch.setattr(
        hub,
        "snapshot_download",
        lambda **kwargs: real_download(endpoint=f"http://127.0.0.1:{server.server_port}", **kwargs),
    )
    try:
        yield calls, commit
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_hub_download_then_cached_reuse_and_job_revision_pin(settings, tmp_path, tiny_hub):
    calls, commit = tiny_hub
    s = configured(settings, tmp_path, ("good",))
    registry = Registry(s)
    model = registry.select("es", [], ["good"])[0]
    snapshot = model_snapshot([model])
    roots = [tmp_path / "job-a", tmp_path / "job-b"]
    for root in roots:
        root.mkdir()
    prepared = ModelCache(s, roots[0]).prepare(model)
    assert not prepared["cache_hit"] and prepared["resolved_revision"] == commit
    assert any(method == "GET" and path.endswith("model.safetensors") for method, path in calls)
    requests = len(calls)
    second = ModelCache(s, roots[1]).prepare(model)
    assert second["cache_hit"] and len(calls) == requests
    assert registry.public("es")[0]["load_state"] == "cached"
    assert model_snapshot(registry.select("es", [], ["good"])) == snapshot
    assert (
        json.loads((roots[0] / "resolved-models.json").read_text())["good"]["resolved_revision"]
        == commit
    )
    offline = s.model_copy(update={"hf_hub_offline": True})
    assert ModelCache(offline, roots[0]).prepare(model)["cache_hit"]
    assert len(calls) == requests


@pytest.mark.parametrize("language", ["es", "oth"])
def test_real_cold_hub_pipeline_and_warm_second_job_without_validation(
    settings, tmp_path, tiny_hub, language
):
    calls, commit = tiny_hub
    s = configured(settings, tmp_path, ("good",))
    if language == "oth":
        catalog = yaml.safe_load(s.model_config_path.read_text())
        catalog["multilingual"] = {
            "entities": {"DISEASE": {"display_name": "Diseases", "models": ["good"]}}
        }
        s.model_config_path.write_text(yaml.safe_dump(catalog))
    s = s.model_copy(update={"rate_limit_seconds": 0.001})
    app = create_app(s)
    with AccountClient(app) as client:
        for number in range(2):
            accepted = client.post(
                "/api/jobs",
                data={
                    "language": language,
                    "other_language": "Turkish" if language == "oth" else "",
                    "models": ["good"],
                },
                files={"files": ("a.txt", "😀 Cancer é.\r\nCancer.".encode())},
            )
            assert accepted.status_code == 202, accepted.text
            job = app.state.db.claim()
            summary = process_job(job, s)
            app.state.db.finish(job["id"], summary)
            assert summary["successful_documents"] == 1 and summary["failed_models"] == 0
            assert summary["models"][0]["resolved_revision"] == commit
            assert summary["models"][0]["label_mapping"]["ENFERMEDAD"] == "DISEASE"
            assert summary["models"][0]["cache_hit"] is bool(number)
            assert summary["tokens"] > 0
            if not number:
                request_count = len(calls)
            else:
                assert len(calls) == request_count
            root = app.state.jobs.storage.job(job["id"])
            record = json.loads(next((root / "published").glob("*/artifact.json")).read_text())
            text = "😀 Cancer é.\r\nCancer."
            assert record["spans"] and all(
                row["label"] == "DISEASE" and row["original_labels"] == ["ENFERMEDAD"]
                for row in record["spans"]
            )
            assert all(
                text[row["start_span"] : row["end_span"]] == row["text"] for row in record["spans"]
            )
            assert (
                client.get("/api/jobs/" + accepted.json()["token"] + "/download/brat").status_code
                == 200
            )


def test_real_missing_hub_model_does_not_cancel_working_classifier(settings, tmp_path, tiny_hub):
    s = configured(settings, tmp_path)
    app = create_app(s)
    with AccountClient(app) as client:
        response = client.post(
            "/api/jobs",
            data={"language": "es", "models": ["bad", "good"]},
            files={"files": ("a.txt", b"Cancer.")},
        )
        job = app.state.db.claim()
        summary = process_job(job, s)
        app.state.db.finish(job["id"], summary)
        assert summary["successful_documents"] == 1 and summary["failed_models"] == 1
        assert summary["model_errors"][0]["model_id"] == "bad"
        assert summary["model_errors"][0]["http_status"] == 404
        assert (
            client.get("/api/jobs/" + response.json()["token"]).json()["status"]
            == "COMPLETED_WITH_ERRORS"
        )


@pytest.mark.skipif(os.environ.get("BROWSER_TESTS") != "1", reason="Actual Chromium opt-in")
def test_browser_can_launch_an_uncached_configured_repository(simple_server):
    from playwright.sync_api import sync_playwright

    base = simple_server
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        def csrf(path):
            return re.search(
                r'name="csrf-token" content="([^"]+)"', page.request.get(base + path).text()
            ).group(1)

        token = csrf("/register")
        assert (
            page.request.post(
                base + "/api/auth/register",
                data={
                    **register_values("cold@example.org"),
                    "password": "abcd",
                    "password_confirmation": "abcd",
                    "csrf_token": token,
                },
            ).status
            == 200
        )
        token = csrf("/login")
        assert (
            page.request.post(
                base + "/api/auth/login",
                data={"email": "cold@example.org", "password": "abcd", "csrf_token": token},
            ).status
            == 200
        )
        page.goto(base + "/annotate")
        page.wait_for_selector('[data-category="DISEASE"] > summary')
        page.locator('[data-category="DISEASE"] > summary').click()
        check = page.locator('input[name="models"][value="bsc-bio-ehr-es-distemist"]')
        assert check.is_enabled()
        assert "Download on first use" in check.locator("..").text_content()
        check.check()
        page.locator("#files").set_input_files(
            {
                "name": "synthetic.txt",
                "mimeType": "text/plain",
                "buffer": b"Synthetic research text.",
            }
        )
        page.locator("#submit").click()
        page.get_by_role("button", name="Continue to request", exact=True).click()
        page.wait_for_url(re.compile(re.escape(base) + r"/jobs/[a-f0-9]+"))
        assert page.request.get(base + "/api/my/jobs").json()[0]["status"] in (
            "QUEUED",
            "PROCESSING",
            "COMPLETED",
        )
        browser.close()
