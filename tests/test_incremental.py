"""Controlled predictors verify mechanics; actual NLP session equivalence is tested separately."""

import json
from unittest.mock import patch

import pytest

from app.api.schemas import Submission
from app.main import create_app
from app.persistence.progress import ProgressRepository
from app.services.pipeline import process_job
from tests.auth_helpers import AccountClient as TestClient


def controlled_stats(documents, spans, language, reference):
    rows = [
        {
            "filename": name,
            "characters": len(text),
            "words": 1,
            "tokens": 1,
            "sentences": 1,
            "entities_total": sum(r["filename"] == name for r in spans),
            "processing_status": "COMPLETED",
        }
        for name, text in documents.items()
    ]
    return {"operational": {"documents": len(documents), "annotations": len(spans)}}, rows


def setup_job(settings, count=3, multi=False):
    settings = settings.model_copy(update={"inference_document_batch_size": 1})
    app = create_app(settings)
    registry = app.state.registry
    for entity in registry.languages["es"]["entities"].values():
        entity["available"] = True
    form = Submission(
        submitter_name="Test",
        submitter_email="test@example.org",
        language="es",
        entities=["DISEASE", "SYMPTOM"] if multi else ["DISEASE"],
    )
    from tests.auth_helpers import acting_as

    with acting_as(app):
        accepted = app.state.jobs.submit(form, [(f"{i}.txt", b"abc") for i in range(count)], "one")
    return app, accepted, app.state.db.claim(), settings


class Predictor:
    def __init__(self, callback=None):
        self.callback = callback
        self.calls = []

    def predict(self, model, documents, output, device):
        self.calls.append((model["model_id"], list(documents)))
        if self.callback:
            self.callback(model, documents)
        return [
            {
                "filename": name,
                "label": model["label"],
                "start_span": 0,
                "end_span": 3,
                "text": text,
                "score": 0.8,
            }
            for name, text in documents.items()
        ], {"model_id": model["model_id"]}


def test_live_document_publication_after_all_models(settings):
    app, accepted, job, s = setup_job(settings, multi=True)
    base = "/api/jobs/" + accepted["token"]
    with TestClient(app) as client:

        def observe(model, documents):
            state = client.get(base + "/progress").json()
            number = int(next(iter(documents)).split(".")[0])
            assert state["annotated_documents"] == number
            assert state["processing_documents"] == 1
            if number:
                rows = client.get(base + "/documents").json()["items"]
                assert rows[0]["status"] == "ANNOTATED"
                identity = rows[0]["document_id"]
                assert client.get(base + "/documents/" + identity).status_code == 200
                assert (
                    len(
                        client.get(base + "/documents/" + identity + "/annotations").json()["items"]
                    )
                    == 2
                )
                assert (
                    client.get(base + "/documents/" + identity + "/download/ann").status_code == 200
                )
                assert client.get(base + "/download/brat").status_code == 409
                assert client.get("/jobs/" + accepted["token"] + "/viewer").status_code == 200

        engine = Predictor(observe)
        summary = process_job(job, s, engine, controlled_stats, lambda _: app.state.registry)
        assert len(engine.calls) == 6
        app.state.db.finish(job["id"], summary)
        assert client.get(base + "/progress").json()["progress_percent"] == 100
        assert client.get(base + "/download/brat").status_code == 200


def test_restart_reuses_verified_publications_without_double_count(settings):
    app, accepted, job, s = setup_job(settings)

    def interrupt(model, documents):
        if "1.txt" in documents:
            raise SystemExit("test interruption")

    with pytest.raises(SystemExit):
        process_job(job, s, Predictor(interrupt), controlled_stats, lambda _: app.state.registry)
    assert (
        ProgressRepository(app.state.db).snapshot(app.state.db.get(accepted["token"]))[
            "annotated_documents"
        ]
        == 1
    )
    app.state.db.recover()
    job = app.state.db.claim()
    engine = Predictor()
    result = process_job(job, s, engine, controlled_stats, lambda _: app.state.registry)
    assert [names for _, names in engine.calls] == [["1.txt"], ["2.txt"]]
    assert result["documents"] == 3
    assert (
        ProgressRepository(app.state.db).snapshot(app.state.db.get(accepted["token"]))[
            "annotated_documents"
        ]
        == 3
    )


def test_partial_failures_are_explicit_and_retained(settings):
    app, accepted, job, s = setup_job(settings)

    def fail(model, documents):
        if "1.txt" in documents:
            raise RuntimeError("controlled failure")

    result = process_job(job, s, Predictor(fail), controlled_stats, lambda _: app.state.registry)
    app.state.db.finish(job["id"], result)
    with TestClient(app) as client:
        base = "/api/jobs/" + accepted["token"]
        status = client.get(base).json()
        assert status["status"] == "COMPLETED_WITH_ERRORS"
        assert status["progress"]["annotated_documents"] == 2
        assert status["progress"]["failed_documents"] == 1
        assert status["progress"]["progress_percent"] == pytest.approx(200 / 3)
        response = client.get(base + "/download/brat")
        assert "partial" in response.headers["content-disposition"]
        root = app.state.jobs.storage.job(job["id"])
        assert json.loads((root / "output" / "manifest.json").read_text())["partial"] is True
        failed = next(
            r for r in client.get(base + "/documents").json()["items"] if r["status"] == "FAILED"
        )
        assert client.get(base + "/documents/" + failed["document_id"]).status_code == 409


def test_atomic_publication_survives_interruption_before_db_commit(settings):
    app, accepted, job, s = setup_job(settings, count=1)

    def interrupted(*args, **kwargs):
        raise SystemExit("after atomic rename")

    with patch.object(ProgressRepository, "publish", interrupted), pytest.raises(SystemExit):
        process_job(job, s, Predictor(), controlled_stats, lambda _: app.state.registry)
    app.state.db.recover()
    job = app.state.db.claim()
    engine = Predictor()
    result = process_job(job, s, engine, controlled_stats, lambda _: app.state.registry)
    assert result["documents"] == 1 and engine.calls == []
    assert ProgressRepository(app.state.db).rows(job["id"])[0]["status"] == "ANNOTATED"


def test_missing_committed_artifact_is_reprocessed(settings):
    import shutil

    app, accepted, job, s = setup_job(settings, count=2)

    def interrupted(model, documents):
        if "1.txt" in documents:
            raise SystemExit("controlled interruption")

    with pytest.raises(SystemExit):
        process_job(job, s, Predictor(interrupted), controlled_stats, lambda _: app.state.registry)
    row = ProgressRepository(app.state.db).rows(job["id"])[0]
    shutil.rmtree(app.state.jobs.storage.job(job["id"]) / "published" / row["document_id"])
    app.state.db.recover()
    job = app.state.db.claim()
    engine = Predictor()
    result = process_job(job, s, engine, controlled_stats, lambda _: app.state.registry)
    assert [names for _, names in engine.calls] == [["0.txt"], ["1.txt"]]
    assert result["documents"] == 2
