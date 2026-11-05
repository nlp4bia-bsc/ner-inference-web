"""Catalog evidence, explicit selections and all-model canonical publication."""

import csv
import io
import json
from unittest.mock import patch

import pytest
import yaml

from app.api.schemas import Submission
from app.errors import ServiceError
from app.main import create_app
from app.services.inference import merge_predictions
from app.services.pipeline import process_job
from app.services.registry import Registry, model_snapshot
from tests.auth_helpers import AccountClient as TestClient
from tests.test_incremental import controlled_stats


@pytest.fixture
def catalog_settings(settings, tmp_path):
    catalog = {
        "languages": {
            "es": {
                "display_name": "Spanish",
                "entities": {
                    "LOCATION": {
                        "display_name": "Locations",
                        "models": ["location-a", "location-b"],
                    }
                },
            },
            "en": {"display_name": "English", "entities": {}},
        },
        "multilingual": {
            "entities": {"LOCATION": {"display_name": "Locations", "models": ["global-location"]}}
        },
        "models": {
            identity: {
                "name": identity,
                "language": "es",
                "languages": languages,
                "target_label": raw,
                "label_mapping": {raw: "LOCATION"},
            }
            for identity, raw, languages in [
                ("location-a", "GPE_NOM", ["es"]),
                ("location-b", "FAC_NOM", ["es"]),
                ("global-location", "GEO_NOM", ["es", "en"]),
            ]
        },
    }
    path = tmp_path / "catalog.yaml"
    path.write_text(yaml.safe_dump(catalog))
    return settings.model_copy(
        update={"model_config_path": path, "inference_document_batch_size": 1}
    )


def available_registry(settings):
    registry = Registry(settings)
    for model in registry.models.values():
        model["available"] = True  # Mechanics fixture, never a production setting.
    return registry


def test_inventory_is_cumulative_and_primary_categories_are_flat(settings):
    registry = Registry(settings)
    categories = registry.languages["es"]["entities"]
    assert {
        "DISEASE",
        "SYMPTOM",
        "MEDICATION",
        "PROCEDURE",
        "ANONYMIZATION",
        "HUMAN",
        "SPECIES",
        "PROFESSION",
        "LOCATION",
        "NEGATION_UNCERTAINTY",
        "TEMPORALITY",
        "EVENT",
        "SITUATION",
    } <= set(categories)
    assert {"es-disease", "es-symptom", "en-disease"} <= registry.models.keys()
    inventory = json.loads(open("catalog/inventory-provenance.json").read())
    assert len(inventory["excel_repositories"]) == 36
    assert all(row["model_id"] in registry.models for row in inventory["excel_repositories"])
    assert all(
        registry.models[row["model_id"]]["repository"] == row["repository"]
        for row in inventory["excel_repositories"]
    )
    greek = registry.models["GreekMedNLP-bert-base-greek-uncased-v1-2025-2026"]
    assert greek["repository"] == "BSC-NLP4BIA/GreekMedNLP-bert-base-greek-uncased-v1-2025-2026"
    assert greek["languages"] == ["el"]
    assert not any(m["available"] for m in registry.models.values())
    locations = [r for r in registry.public("es") if r["entity"] == "LOCATION"]
    assert {r["model_id"] for r in locations} == {"location-tagger", "location-sub-tagger"}
    assert not any(
        r["display_name"].lower() in ("others", "other entity types") for r in registry.public()
    )
    for row in registry.public():
        assert not any(
            word in row.get("model_name", "").lower()
            for word in ("best model", "recommended model", "top model", "best f1", "best verified")
        )
        assert "model_dir" not in row
    assert any(
        r["language"] == "mul" for r in registry.public("el")
    )  # Section remains discoverable.


def test_explicit_multi_checkpoint_selection_and_language_guards(catalog_settings):
    registry = available_registry(catalog_settings)
    selected = registry.select("es", [], ["location-b", "global-location", "location-a"])
    assert [m["model_id"] for m in selected] == ["location-b", "global-location", "location-a"]
    assert {m["label"] for m in selected} == {"LOCATION"}
    assert registry.select("en", [], ["global-location"])[0]["model_id"] == "global-location"
    for language, entities, models in [
        ("es", ["LOCATION"], None),
        ("es", [], []),
        ("es", [], ["location-a", "location-a"]),
        ("es", [], ["unknown"]),
        ("en", [], ["location-a"]),
        ("es", ["DISEASE"], ["location-a"]),
    ]:
        with pytest.raises(ServiceError):
            registry.select(language, entities, models)


def test_dependency_graph_rejects_cycles_and_never_runs_unknown_task(catalog_settings):
    path = catalog_settings.model_config_path
    catalog = yaml.safe_load(path.read_text())
    catalog["models"]["location-b"].update(task="span_classification", requires=["location-a"])
    path.write_text(yaml.safe_dump(catalog))
    registry = Registry(catalog_settings)
    assert registry._dependency_order(["location-b"]) == ["location-a", "location-b"]
    assert not registry.models["location-b"]["available"]
    with pytest.raises(ServiceError):
        registry.select("es", [], ["location-b"])
    catalog["models"]["location-a"]["requires"] = ["location-b"]
    path.write_text(yaml.safe_dump(catalog))
    with pytest.raises(ValueError, match="Cyclic"):
        Registry(catalog_settings)


def test_consolidation_retains_original_labels_scores_and_all_overlaps():
    text = "😀 Madrid Norte"

    def span(label, start=2, end=8, score=0.8):
        return {
            "filename": "a.txt",
            "label": label,
            "start_span": start,
            "end_span": end,
            "text": text[start:end],
            "score": score,
        }

    a = {
        "label": "LOCATION",
        "model_id": "a",
        "version": "1",
        "label_mapping": {"GPE_NOM": "LOCATION"},
    }
    b = {
        "label": "LOCATION",
        "model_id": "b",
        "version": "2",
        "label_mapping": {"FAC_NOM": "LOCATION"},
    }
    batches = [
        (a, [span("GPE_NOM"), span("GPE_NOM", 2, 11)]),
        (b, [span("FAC_NOM", score=0.9), span("FAC_NOM", 6, 13)]),
    ]
    merged = merge_predictions({"a.txt": text}, batches)
    assert merged == merge_predictions({"a.txt": text}, list(reversed(batches)))
    assert len(merged) == 3
    shared = next(r for r in merged if (r["start_span"], r["end_span"]) == (2, 8))
    assert shared["model_ids"] == ["a", "b"]
    assert shared["original_labels"] == ["FAC_NOM", "GPE_NOM"]
    assert [s["score"] for s in shared["sources"]] == [0.8, 0.9]
    assert shared["model_id"] == "b" and shared["score"] == 0.9


def test_explicit_models_publish_one_span_and_export_all_sources(catalog_settings):
    app = create_app(catalog_settings)
    registry = app.state.registry
    for model in registry.models.values():
        model["available"] = True
    base = None
    with TestClient(app) as client:
        accepted = client.post(
            "/api/jobs",
            data={
                "submitter_name": "Test",
                "submitter_email": "test@example.org",
                "language": "es",
                "models": ["location-a", "location-b", "global-location"],
            },
            files={"files": ("a.txt", b"Madrid Norte")},
        )
        assert accepted.status_code == 202, accepted.text
        base = "/api/jobs/" + accepted.json()["token"]
        assert client.get(base).json()["entities"] == ["LOCATION"]
        assert len(client.get(base).json()["models"]) == 3
        job = app.state.db.claim()

        class Predictor:
            def predict(self, model, documents, output, device):
                assert client.get(base + "/progress").json()["annotated_documents"] == 0
                return [
                    {
                        "filename": name,
                        "label": model["target_label"],
                        "start_span": 0,
                        "end_span": 6,
                        "text": text[:6],
                        "score": 0.9,
                    }
                    for name, text in documents.items()
                ], {"model_id": model["model_id"]}

        with patch("app.services.pipeline.Registry", return_value=registry):
            summary = process_job(
                job,
                catalog_settings,
                Predictor(),
                controlled_stats,
                registry_factory=lambda _: registry,
            )
        app.state.db.finish(job["id"], summary)
        doc = client.get(base + "/documents").json()["items"][0]
        annotations = client.get(base + "/documents/" + doc["document_id"] + "/annotations").json()[
            "items"
        ]
        assert len(annotations) == 1 and len(annotations[0]["sources"]) == 3
        assert annotations[0]["label"] == "LOCATION"
        rows = list(
            csv.DictReader(io.StringIO(client.get(base + "/download/tsv").text), delimiter="\t")
        )
        assert len(rows) == 1 and len(json.loads(rows[0]["sources"])) == 3
        assert (
            client.get(base + "/documents/" + doc["document_id"] + "/download/ann").text.count(
                "\tLOCATION "
            )
            == 1
        )


def test_mapping_snapshot_changes_fail_and_legacy_snapshots_still_work(settings):
    app = create_app(settings)
    registry = app.state.registry
    registry.models["es-disease"]["available"] = True
    from tests.auth_helpers import acting_as

    with acting_as(app):
        accepted = app.state.jobs.submit(
            Submission(
                submitter_name="Test",
                submitter_email="x@example.org",
                language="es",
                entities=["DISEASE"],
            ),
            [("a.txt", b"abc")],
            "ip",
        )
    job = app.state.db.claim()
    payload = json.loads(job["payload"])
    assert payload["catalog_version"] == 2
    # Simulate a pre-correction pending job; model selection/digests keep their old contract.
    payload.pop("catalog_version")
    payload["selected_models"] = model_snapshot(registry.select("es", ["DISEASE"]), legacy=True)
    legacy_job = {**job, "payload": json.dumps(payload)}
    from tests.test_incremental import Predictor

    with patch("app.services.pipeline.Registry", return_value=registry):
        process_job(
            legacy_job, settings, Predictor(), controlled_stats, registry_factory=lambda _: registry
        )
        registry.models["es-disease"]["label_mapping"] = {"ENTITY": "DISEASE"}
        with pytest.raises(ValueError, match="registry changed"):
            process_job(
                job, settings, Predictor(), controlled_stats, registry_factory=lambda _: registry
            )
    with acting_as(app):
        assert app.state.jobs.available(accepted["token"])


def test_dependent_stage_receives_upstream_spans_and_is_not_called_as_detector(catalog_settings):
    catalog = yaml.safe_load(catalog_settings.model_config_path.read_text())
    catalog["models"]["location-b"].update(task="span_classification", requires=["location-a"])
    catalog_settings.model_config_path.write_text(yaml.safe_dump(catalog))
    app = create_app(catalog_settings)
    registry = app.state.registry
    for model in registry.models.values():
        model["available"] = True  # Controlled dependency-aware fixture only.
    from tests.auth_helpers import acting_as

    with acting_as(app):
        app.state.jobs.submit(
            Submission(
                submitter_name="Test",
                submitter_email="dep@example.org",
                language="es",
                models=["location-b"],
            ),
            [("a.txt", b"Madrid")],
            "dep",
        )
    job = app.state.db.claim()
    calls = []

    class Engine:
        def predict(self, model, documents, output, device):
            assert model["model_id"] == "location-a"
            calls.append("detector")
            return [
                {
                    "filename": "a.txt",
                    "label": "GPE_NOM",
                    "start_span": 0,
                    "end_span": 6,
                    "text": "Madrid",
                    "score": 0.7,
                }
            ], {}

        def classify(self, model, documents, upstream, device):
            assert model["model_id"] == "location-b"
            assert upstream["location-a"][0]["text"] == "Madrid"
            calls.append("classifier")
            return [{**upstream["location-a"][0], "label": "FAC_NOM"}], {}

    process_job(
        job, catalog_settings, Engine(), controlled_stats, registry_factory=lambda _: registry
    )
    assert calls == ["detector", "classifier"]


def test_actual_native_checkpoints_support_explicit_same_category_selection(settings, tmp_path):
    import os
    import subprocess
    import sys

    from app.services.inference import NerLabSession
    from tests.test_real_inference import build_checkpoint

    checkpoint = build_checkpoint(tmp_path)
    catalog = {
        "languages": {
            "es": {
                "display_name": "Spanish",
                "entities": {
                    "FINDING": {"display_name": "Findings", "models": ["native-a", "native-b"]}
                },
            }
        },
        "models": {
            identity: {
                "language": "es",
                "languages": ["es"],
                "target_label": "DISEASE",
                "label_mapping": {"DISEASE": "FINDING"},
                "enabled": True,
                "model_dir": str(checkpoint),
            }
            for identity in ["native-a", "native-b"]
        },
    }
    path = tmp_path / "native.yaml"
    path.write_text(yaml.safe_dump(catalog))
    receipt = tmp_path / "receipts.json"
    s = settings.model_copy(update={"model_config_path": path, "model_validation_path": receipt})
    run = subprocess.run(
        [sys.executable, "-m", "scripts.validate_models"],
        env={
            **os.environ,
            "MODEL_CONFIG_PATH": str(path),
            "MODEL_VALIDATION_PATH": str(receipt),
            "DEVICE": "cpu",
            "OMP_NUM_THREADS": "1",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stderr
    registry = Registry(s)
    models = registry.select("es", [], ["native-a", "native-b"])
    session = NerLabSession(1)
    predictions = []
    try:
        for model in models:
            rows, _ = session.predict(model, {"a.txt": "Cancer."}, tmp_path / "unused", "cpu")
            predictions.append((model, rows))
        merged = merge_predictions({"a.txt": "Cancer."}, predictions)
        assert merged and all(
            r["label"] == "FINDING" and r["model_ids"] == ["native-a", "native-b"] for r in merged
        )
    finally:
        session.close()
    # A changed canonical mapping cannot reuse a receipt for another contract.
    catalog["languages"]["es"]["entities"] = {
        "DISEASE": {"display_name": "Diseases", "models": ["native-a", "native-b"]}
    }
    for e in catalog["models"].values():
        e["label_mapping"] = {"DISEASE": "DISEASE"}
    path.write_text(yaml.safe_dump(catalog))
    assert not any(e["available"] for e in Registry(s).models.values())
