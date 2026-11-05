"""Real ner_lab statistics with a synthetic local tokenizer; no pretrained model."""

import json

import pytest

from app.services.statistics import statistics


def test_real_library_statistics(tmp_path):
    pytest.importorskip("lab")
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from transformers import PreTrainedTokenizerFast

    tokenizer = Tokenizer(
        WordLevel({"[UNK]": 0, "Cancer": 1, ".": 2, "Nada": 3}, unk_token="[UNK]")
    )
    tokenizer.pre_tokenizer = Whitespace()
    saved = tmp_path / "tokenizer"
    PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]").save_pretrained(saved)
    stats, per_doc = statistics(
        {"a.txt": "Cancer.\r\n", "b.txt": "Nada."},
        [
            {
                "filename": "a.txt",
                "label": "DISEASE",
                "start_span": 0,
                "end_span": 6,
                "text": "Cancer",
                "score": 0.9,
            }
        ],
        "es",
        str(saved),
    )
    assert stats["ner_lab"]["text"]["documents"] == 2
    assert stats["ner_lab"]["text"]["words"] == 2
    assert stats["ner_lab"]["annotations"]["mentions"] == 1
    assert sum(r["tokens"] for r in per_doc) == stats["ner_lab"]["text"]["tokens"]
    assert sum(r["words"] for r in per_doc) == stats["ner_lab"]["text"]["words"]
    json.dumps(stats, allow_nan=False)
