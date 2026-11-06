"""CPU integration with a tiny randomly initialized local BERT, never a clinical model."""

import json
import os
import subprocess
import sys
import time

import pytest
import yaml

from app.main import create_app
from tests.auth_helpers import AccountClient as TestClient
from tests.conftest import submit


def test_real_preflight_worker_and_ner_lab(settings, tmp_path):
    checkpoint = build_checkpoint(tmp_path)
    catalog = tmp_path / "models.yaml"
    catalog.write_text(
        yaml.safe_dump(
            {
                "languages": {
                    "es": {
                        "display_name": "Spanish",
                        "entities": {
                            "DISEASE": {
                                "display_name": "Diseases",
                                "model_id": "synthetic-test-only",
                                "enabled": True,
                                "model_dir": str(checkpoint),
                            }
                        },
                    }
                }
            }
        )
    )
    receipt = tmp_path / "validated.json"
    s = settings.model_copy(
        update={"model_config_path": catalog, "model_validation_path": receipt, "device": "cpu"}
    )
    env = {
        **os.environ,
        "STORAGE_ROOT": str(s.storage_root),
        "MODEL_CONFIG_PATH": str(catalog),
        "MODEL_VALIDATION_PATH": str(receipt),
        "DEVICE": "cpu",
        "MODEL_LOADING_MODE": "validated_local",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "OMP_NUM_THREADS": "1",
    }
    result = subprocess.run(
        [sys.executable, "-m", "scripts.validate_models"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    with TestClient(create_app(s)) as client:
        accepted = submit(client)
        assert accepted.status_code == 202
        token = accepted.json()["token"]
        log_path = tmp_path / "worker.log"
        with log_path.open("w") as log:
            worker = subprocess.Popen(
                [sys.executable, "-m", "app.worker"], env=env, stdout=log, stderr=log
            )
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    data = client.get("/api/jobs/" + token).json()
                    if data["status"] in ("COMPLETED", "FAILED"):
                        break
                    time.sleep(0.1)
                assert data["status"] == "COMPLETED", log_path.read_text()
                assert client.get("/api/jobs/" + token + "/download/brat").status_code == 200
                assert (
                    client.get("/api/jobs/" + token + "/statistics").json()["ner_lab"]["text"][
                        "documents"
                    ]
                    == 1
                )
                second = subprocess.run(
                    [sys.executable, "-m", "app.worker"],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                assert second.returncode != 0 and "already active" in second.stderr
            finally:
                worker.terminate()
                worker.wait(timeout=10)


def build_checkpoint(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("lab")
    pytest.importorskip("datasets")
    pytest.importorskip("accelerate")
    from lab.ner.encoding import Encoder, describe_encoder
    from tokenizers import Tokenizer
    from tokenizers.models import WordPiece
    from tokenizers.pre_tokenizers import BertPreTokenizer
    from tokenizers.processors import TemplateProcessing
    from transformers import BertConfig, BertForTokenClassification, PreTrainedTokenizerFast

    checkpoint = tmp_path / "synthetic-checkpoint"
    vocab = {"[PAD]": 0, "[UNK]": 1, "[CLS]": 2, "[SEP]": 3, "Cancer": 4, ".": 5}
    raw = Tokenizer(WordPiece(vocab=vocab, unk_token="[UNK]"))
    raw.pre_tokenizer = BertPreTokenizer()
    raw.post_processor = TemplateProcessing(
        single="[CLS] $A [SEP]", special_tokens=[("[CLS]", 2), ("[SEP]", 3)]
    )
    tokenizer = PreTrainedTokenizerFast(
        tokenizer_object=raw,
        unk_token="[UNK]",
        pad_token="[PAD]",
        cls_token="[CLS]",
        sep_token="[SEP]",
    )
    encoder = Encoder(tokenizer, "DISEASE", "es", max_length=32, min_sentence_tokens=1)
    torch.manual_seed(42)
    config = BertConfig(
        vocab_size=len(vocab),
        hidden_size=16,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=32,
        max_position_embeddings=64,
        label2id=encoder.label2id,
        id2label=encoder.id2label,
    )
    model = BertForTokenClassification(config)
    model.save_pretrained(checkpoint)
    tokenizer.save_pretrained(checkpoint)
    (checkpoint / "encoding.json").write_text(
        json.dumps(
            {
                "model": {"architecture": "linear", "base_model": str(checkpoint)},
                "encoding": describe_encoder(encoder),
            }
        )
    )
    return checkpoint
