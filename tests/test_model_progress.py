"""Observe real native batches before publication, with private and durable progress."""

import json
import time

import pytest

from app.persistence.job_locks import JobContentChanged
from app.persistence.model_progress import ModelProgressRepository
from app.services.inference import NerLabSession
from app.services.inference_progress import prediction_trainer
from app.services.pipeline import process_job
from tests.auth_helpers import AccountClient, authenticate
from tests.test_document_management import application, upload
from tests.test_incremental import Predictor, controlled_stats
from tests.test_real_inference import build_checkpoint


def test_progress_is_visible_inside_a_model_before_documents_are_published(settings):
    app = application(settings)
    with AccountClient(app) as client:
        identity = upload(client, 2).json()["job_id"]
        queued = client.get(f"/api/jobs/{identity}/progress").json()
        assert queued["worker"]["state"] == "unavailable"
        assert queued["models"][0]["status"] == "PENDING"
        job = app.state.db.claim()
        app.state.db.heartbeat()

        class ObservedPredictor(Predictor):
            on_progress = None

            def predict(self, *args):
                self.on_progress("INFERENCE", 1, 4, "windows")
                progress = client.get(f"/api/jobs/{identity}/progress").json()
                assert progress["worker"]["state"] == "busy"
                assert progress["annotated_documents"] == 0
                assert progress["inference_percent"] == 25
                assert progress["models"][0]["completed_units"] == 1
                assert progress["models"][0]["batch_index"] == 1
                return super().predict(*args)

        summary = process_job(
            job,
            settings,
            ObservedPredictor(),
            controlled_stats,
            registry_factory=lambda _: app.state.registry,
        )
        app.state.db.finish(identity, summary, claimed_version=job["content_version"])
        result = client.get(f"/api/jobs/{identity}/progress").json()
        assert result["models"][0]["status"] == "COMPLETED"
        assert result["inference_percent"] == 100
        assert result["annotated_documents"] == 2
        # No cross-account IDs/activity details in the service heartbeat.
        assert set(result["worker"]) == {"state", "available", "last_seen_at", "age_seconds"}


def test_failure_restart_and_generation_guards(settings):
    app = application(settings)
    with AccountClient(app) as client:
        identity = upload(client, 3).json()["job_id"]
        job = app.state.db.claim()
        reporter = ModelProgressRepository(app.state.db, job)
        models = [{"model_id": "a"}, {"model_id": "b"}]
        reporter.initialize(models, 3, 2)
        reporter.start_batch("a", 1, 2)
        reporter.complete_batch("a", 2)
        reporter.fail("b", ValueError("PRIVATE CONTENT"), 2)
        rows = ModelProgressRepository.snapshot(app.state.db, job)
        assert rows[0]["completed_documents"] == 2
        assert rows[1]["failed_documents"] == 2 and rows[1]["error_code"] == "ValueError"
        assert "PRIVATE CONTENT" not in json.dumps(rows)
        reporter.initialize(models, 3, 2, resumed=2)
        assert ModelProgressRepository.snapshot(app.state.db, job)[1]["failed_documents"] == 0
        doc = client.get(f"/api/jobs/{identity}/documents").json()["items"][0]
        assert (
            client.delete(f"/api/jobs/{identity}/documents/{doc['document_id']}").status_code == 200
        )
        assert (
            client.get(f"/api/jobs/{identity}/progress").json()["models"][0]["total_documents"] == 2
        )
        app.state.db.finish(identity, failed=True, claimed_version=job["content_version"])
        replacement = app.state.db.claim()
        new = ModelProgressRepository(app.state.db, replacement)
        new.initialize(models, 2, 2)
        with pytest.raises(JobContentChanged):
            reporter.ensure("a", 3)
        with pytest.raises(JobContentChanged):
            reporter.update("a", "INFERENCE", 3, 3, "windows")
        ModelProgressRepository.interrupt(app.state.db, job, "OldWorker")
        assert all(r["status"] == "PENDING" for r in new.snapshot(app.state.db, replacement))


def test_queue_reports_fresh_and_stale_worker_without_exposing_foreign_jobs(settings):
    app = application(settings)
    settings.rate_limit_seconds = 0
    with AccountClient(app) as client:
        first = upload(client, 1).json()["job_id"]
        other = upload(client, 1).json()["job_id"]
        app.state.db.claim()
        app.state.db.heartbeat()
        response = client.get(f"/api/jobs/{other}/progress")
        assert response.json()["worker"]["state"] == "busy"
        assert first not in response.text
        with app.state.db.connect() as connection:
            connection.execute(
                "UPDATE runtime SET value=? WHERE key='worker_heartbeat'", (str(time.time() - 30),)
            )
        assert client.get(f"/api/jobs/{other}/progress").json()["worker"]["state"] == "unavailable"
        authenticate(client, "other-owner@example.org")
        assert client.get(f"/api/jobs/{other}/progress").status_code == 404


def test_native_prediction_batches_preserve_outputs_and_run_once(tmp_path):
    checkpoint = build_checkpoint(tmp_path)
    model = {
        "model_dir": str(checkpoint),
        "model_id": "tiny",
        "language": "es",
        "label": "DISEASE",
        "batch_size": 1,
    }
    documents = {f"{i}.txt": "Cancer." for i in range(3)}
    session = NerLabSession()
    expected, _ = session.predict(model, documents, tmp_path / "first", "cpu")
    events = []
    session.on_progress = lambda *event: events.append(event)
    weights = next(iter(session.cache.values()))[0]
    forwards = []
    handle = weights.register_forward_hook(lambda *args: forwards.append(1))
    try:
        actual, meta = session.predict(model, documents, tmp_path / "second", "cpu")
    finally:
        handle.remove()
        session.close()
    assert actual == expected
    updates = [event for event in events if event[0] == "INFERENCE"]
    assert [event[1] for event in updates] == [0, 1, 2, 3]
    assert len(forwards) == meta["n_windows"] == 3
    assert updates[-1] == ("INFERENCE", 3, 3, "windows")


def test_crf_reporting_keeps_native_viterbi_trainer():
    pytest.importorskip("lab")
    from lab.ner.training.trainer import CRFTrainer

    class CRF:
        decode_from_emissions = True

    assert issubclass(prediction_trainer(CRF(), lambda *args: None, 1), CRFTrainer)


def test_reused_publications_restore_each_members_real_outcome(settings):
    app = application(settings)
    with AccountClient(app) as client:
        assert upload(client, 2).status_code == 202
        job = app.state.db.claim()
        reporter = ModelProgressRepository(app.state.db, job)
        reporter.initialize([{"model_id": "a"}, {"model_id": "b"}], 2, 2)
        reporter.restore_document(
            [{"model_id": "a"}, {"model_id": "b", "status": "FAILED", "error_code": "ValueError"}]
        )
        reporter.restore_document([{"model_id": "a"}, {"model_id": "b"}])
        reporter.finish()
        rows = reporter.snapshot(app.state.db, job)
        assert rows[0]["completed_documents"] == 2 and rows[0]["failed_documents"] == 0
        assert rows[1]["completed_documents"] == rows[1]["failed_documents"] == 1
        assert rows[1]["status"] == "COMPLETED_WITH_ERRORS"
