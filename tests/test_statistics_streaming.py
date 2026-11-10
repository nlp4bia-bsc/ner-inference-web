import pytest

from app.services.statistics import StreamingStatistics, statistics


@pytest.mark.parametrize("language", ["es", "oth"])
def test_streamed_native_statistics_match_public_aggregators(tmp_path, language):
    pytest.importorskip("lab")
    from tests.test_real_inference import build_checkpoint

    path = build_checkpoint(tmp_path)
    docs = {"one": "Cancer.\r\n", "two": "Cancer. Cancer."}
    spans = [
        {
            "filename": name,
            "label": "DISEASE",
            "start_span": 0,
            "end_span": 6,
            "text": "Cancer",
            "score": 0.8,
        }
        for name in docs
    ]
    expected, rows = statistics(docs, spans, language, str(path))
    accumulator = StreamingStatistics(language, str(path))
    actual_rows = []
    for name, text in docs.items():
        actual_rows.append(accumulator.add(name, text, [r for r in spans if r["filename"] == name]))
    actual = accumulator.result()
    assert actual["ner_lab"] == expected["ner_lab"]
    assert actual_rows == rows
    assert actual["ner_lab"]["text"]["language"] == language
    assert actual["definitions"]["sentence_language"] == ("en" if language == "oth" else language)
