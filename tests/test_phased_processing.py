"""Observable corpus-wide model/category phases and durable restart boundaries."""

import json

import pytest

from app.persistence.model_progress import ModelProgressRepository
from app.services.normalization import NormalizationSession
from app.services.pipeline import process_job
from scripts.import_gazetteers import import_sources
from tests.auth_helpers import AccountClient
from tests.test_incremental import Predictor, controlled_stats, setup_job


def test_uploaded_documents_are_readable_in_queue_and_after_total_ner_failure(settings):
    app, accepted, job, s = setup_job(settings, count=2)
    base = "/api/jobs/" + accepted["token"]
    with AccountClient(app) as client:
        docs = client.get(base + "/documents").json()["items"]
        for doc in docs:
            endpoint = base + "/documents/" + doc["document_id"]
            assert client.get(endpoint).json()["text"] == "abc"
            assert client.get(endpoint + "/annotations").json()["items"] == []
            assert client.get(endpoint + "/download/ann").status_code == 200

        def fail(*args):
            raise RuntimeError("Synthetic inference failure")

        with pytest.raises(ValueError, match="No documents completed"):
            process_job(job, s, Predictor(fail), controlled_stats, lambda _: app.state.registry)
        app.state.db.finish(job["id"], failed=True)
        assert client.get(base + "/documents/" + docs[0]["document_id"]).status_code == 200


def test_categories_publish_before_next_category_and_resume_without_repeating_ner(
    settings, tmp_path, monkeypatch
):
    import pandas as pd

    settings.normalization_gazetteer_dir = tmp_path / "gazetteers"
    for entity in ("disease", "symptom"):
        path = tmp_path / (entity + ".parquet")
        pd.DataFrame({"term": ["abc"], "code": ["123"], "language": ["es"]}).to_parquet(path)
        import_sources(path, settings)
    app, accepted, job, s = setup_job(settings, count=3, multi=True)
    payload = json.loads(job["payload"])
    from app.services.normalization_catalog import NormalizationCatalog

    payload.update(
        normalize=True,
        normalization_method="levenshtein",
        normalization_threshold=0.8,
        normalization_resources=NormalizationCatalog(s).snapshot(
            "es", payload["entities"], "levenshtein"
        ),
    )
    with app.state.db.connect() as connection:
        connection.execute("UPDATE jobs SET payload=? WHERE id=?", (json.dumps(payload), job["id"]))
    job = app.state.db.get(job["id"])
    base = "/api/jobs/" + accepted["token"]
    normalize = NormalizationSession.normalize
    events = []
    with AccountClient(app) as client:

        def observed(session, spans, language, on_error):
            entity = spans[0]["label"]
            events.append(entity)
            if entity == "SYMPTOM":
                docs = client.get(base + "/documents").json()["items"]
                assert len(docs) == 3
                for doc in docs:
                    rows = client.get(
                        base + "/documents/" + doc["document_id"] + "/annotations"
                    ).json()["items"]
                    assert {row["label"] for row in rows} == {"DISEASE", "SYMPTOM"}
                    disease = next(row for row in rows if row["label"] == "DISEASE")
                    assert disease["normalization"]["code"] == "123"
                progress = client.get(base + "/progress").json()
                assert progress["partial_results"] and progress["mentions"] == 6
                assert progress["publication_revision"] > 0
                raise SystemExit("Synthetic interruption during next category")
            return normalize(session, spans, language, on_error)

        monkeypatch.setattr(NormalizationSession, "normalize", observed)
        engine = Predictor()
        with pytest.raises(SystemExit):
            process_job(job, s, engine, controlled_stats, lambda _: app.state.registry)
        assert events == ["DISEASE"] * 3 + ["SYMPTOM"]
        assert len(engine.calls) == 6
        ModelProgressRepository.interrupt(app.state.db, job, "JobTimeout")
        # The preview remains readable even when the supervisor reports failure.
        docs = client.get(base + "/documents").json()["items"]
        assert all(doc["annotation_count"] == 2 for doc in docs)
        app.state.db.recover()
        replacement = app.state.db.claim()
        monkeypatch.setattr(NormalizationSession, "normalize", normalize)
        resumed = Predictor()
        summary = process_job(
            replacement, s, resumed, controlled_stats, lambda _: app.state.registry
        )
        assert not resumed.calls and summary["annotations"] == 6
        app.state.db.finish(job["id"], summary)
        for doc in docs:
            result = client.get(base + "/documents/" + doc["document_id"] + "/annotations").json()
            assert result["revision"]
            assert all(row["normalization"] for row in result["items"])


def test_supervisor_failure_preserves_ner_preview_and_completed_model(settings):
    app, accepted, job, s = setup_job(settings, count=2, multi=True)
    base = "/api/jobs/" + accepted["token"]

    def interrupt(model, documents):
        if model["model_id"] == "es-symptom":
            raise SystemExit("Synthetic timeout")

    with AccountClient(app) as client:
        with pytest.raises(SystemExit):
            process_job(
                job, s, Predictor(interrupt), controlled_stats, lambda _: app.state.registry
            )
        ModelProgressRepository.interrupt(app.state.db, job, "JobTimeout")
        app.state.db.finish(job["id"], failed=True)
        snapshot = client.get(base + "/progress").json()
        assert snapshot["status"] == "FAILED" and snapshot["partial_results"]
        assert snapshot["mentions"] == 2 and snapshot["annotated_documents"] == 0
        assert snapshot["models"][0]["status"] == "COMPLETED"
        assert snapshot["models"][1]["error_code"] == "JobTimeout"
        docs = client.get(base + "/documents").json()["items"]
        for doc in docs:
            result = client.get(base + "/documents/" + doc["document_id"] + "/annotations").json()
            assert [span["label"] for span in result["items"]] == ["DISEASE"]


def test_restart_repairs_preview_committed_before_counts_and_skips_saved_member(settings):
    from unittest.mock import patch

    from app.persistence.progress import ProgressRepository

    app, accepted, job, s = setup_job(settings, count=2, multi=True)
    with patch.object(ProgressRepository, "preview", side_effect=SystemExit("Synthetic crash")):
        with pytest.raises(SystemExit):
            process_job(job, s, Predictor(), controlled_stats, lambda _: app.state.registry)
    app.state.db.recover()
    replacement = app.state.db.claim()
    engine = Predictor()
    summary = process_job(replacement, s, engine, controlled_stats, lambda _: app.state.registry)
    assert engine.calls == [
        ("es-disease", ["1.txt"]),
        ("es-symptom", ["0.txt"]),
        ("es-symptom", ["1.txt"]),
    ]
    assert summary["annotations"] == 4
    assert (
        ProgressRepository(app.state.db).snapshot(app.state.db.get(accepted["token"]))[
            "annotated_documents"
        ]
        == 2
    )
