import json
from unittest.mock import patch

import pytest

from app.services.registry import Registry
from app.worker import process_job
from tests.conftest import submit


def test_queued_pipeline_with_real_statistics_and_controlled_predictions(client, tmp_path):
    pytest.importorskip("lab")
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from transformers import PreTrainedTokenizerFast

    tokenizer = Tokenizer(WordLevel({"[UNK]": 0, "Cancer": 1, ".": 2}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    saved = tmp_path / "checkpoint"
    PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]").save_pretrained(saved)
    entity = client.app.state.registry.languages["es"]["entities"]["DISEASE"]
    entity["model_dir"] = str(saved)
    accepted = submit(client).json()
    db = client.app.state.db
    job = db.claim()
    assert client.get("/api/jobs/" + accepted["token"]).json()["status"] == "PROCESSING"
    registry = client.app.state.registry
    registry.languages["es"]["statistics_model"] = str(saved)

    class ControlledPredictor:
        def predict(self, model, documents, output, device):
            assert list(documents) == ["a.txt"]
            return [
                {
                    "filename": "a.txt",
                    "label": "DISEASE",
                    "start_span": 0,
                    "end_span": 6,
                    "text": "Cancer",
                    "score": 0.9,
                }
            ], {"model_id": "test-only-controlled-data"}

    with patch("app.worker.Registry", return_value=registry):
        summary = process_job(job, client.app.state.settings, ControlledPredictor())
    db.finish(job["id"], summary)
    assert client.get("/api/jobs/" + accepted["token"]).json()["downloads_available"]
    assert client.get("/api/jobs/" + accepted["token"] + "/download/brat").status_code == 200
    assert "Cancer" in client.get("/api/jobs/" + accepted["token"] + "/download/tsv").text
    assert (
        client.get("/api/jobs/" + accepted["token"] + "/statistics").json()["operational"][
            "annotations"
        ]
        == 1
    )


def test_registry_requires_validation_receipt(settings, tmp_path):
    import yaml

    path = tmp_path / "checkpoint"
    path.mkdir()
    (path / "encoding.json").write_text(
        json.dumps(
            {
                "model": {"architecture": "linear"},
                "encoding": {"language": "es", "target_label": "DISEASE", "label2id": {"O": 0}},
            }
        )
    )
    (path / "tokenizer.json").write_text("{}")
    (path / "model.safetensors").write_bytes(b"not actual weights")
    config = tmp_path / "models.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "languages": {
                    "es": {
                        "display_name": "Spanish",
                        "entities": {
                            "DISEASE": {
                                "display_name": "Diseases",
                                "model_id": "test",
                                "enabled": True,
                                "model_dir": str(path),
                            }
                        },
                    }
                }
            }
        )
    )
    registry = Registry(settings.model_copy(update={"model_config_path": config}))
    # Existing files and encoding are insufficient; preflight must actually initialize it.
    assert registry.public()[0]["available"] is False
    assert "model_dir" not in registry.public()[0]


def test_failed_job_never_downloadable(client):
    data = submit(client).json()
    db = client.app.state.db
    db.claim()
    db.finish(data["job_id"], failed=True)
    assert client.get("/api/jobs/" + data["token"]).json()["status"] == "FAILED"
    assert client.get("/api/jobs/" + data["token"] + "/download/brat").status_code == 409
