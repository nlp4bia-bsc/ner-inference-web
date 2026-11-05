import csv
import io
import json
import zipfile

import pytest

from app.services.export import package
from app.services.inference import merge_predictions


def span(**values):
    return {
        "filename": "a.txt",
        "label": "DISEASE",
        "start_span": 2,
        "end_span": 8,
        "text": "cáncer",
        "score": 0.8,
        **values,
    }


def test_merge_duplicates_and_overlap():
    docs = {"a.txt": "😀 cáncer.\r\n"}
    rows = [span(score=0.2), span(score=0.9), span(start_span=2, end_span=5, text="cán", score=0.5)]
    result = merge_predictions(
        docs,
        [
            ({"label": "DISEASE", "model_id": "one"}, rows),
            ({"label": "SYMPTOM", "model_id": "two"}, [span(label="SYMPTOM")]),
        ],
    )
    assert len(result) == 3
    assert next(x for x in result if x["end_span"] == 8 and x["label"] == "DISEASE")["score"] == 0.9


@pytest.mark.parametrize(
    "change",
    [
        {"start_span": -1},
        {"end_span": 100},
        {"text": "wrong"},
        {"score": float("nan")},
        {"label": "OTHER"},
        {"filename": "missing"},
        {"start_span": 2.5},
    ],
)
def test_bad_offsets_fail(change):
    with pytest.raises((ValueError, KeyError)):
        merge_predictions(
            {"a.txt": "😀 cáncer."}, [({"label": "DISEASE", "model_id": "m"}, [span(**change)])]
        )


def test_brat_tsv_originals_empty_ann(tmp_path):
    docs = {"nested/a.txt": "😀 cáncer.\r\n".encode(), "other/a.txt": b"Nothing here."}
    spans = [
        {**span(filename="nested/a.txt"), "model_id": "m"},
        {**span(filename="nested/a.txt", label="SYMPTOM"), "model_id": "m2"},
    ]
    payload = {
        "entities": ["DISEASE", "SYMPTOM"],
        "language": "es",
        "submitter_name": "A",
        "submitter_email": "a@example.org",
    }
    package(tmp_path, docs, spans, payload, {}, [], {"job_id": "id"})
    with zipfile.ZipFile(tmp_path / "results.zip") as z:
        assert z.read("brat/documents/nested/a.txt") == docs["nested/a.txt"]
        assert z.read("brat/documents/other/a.ann") == b""
        ann = z.read("brat/documents/nested/a.ann").decode().splitlines()
        assert len(ann) == 2 and ann[0].startswith("T1\t") and ann[1].startswith("T2\t")
        for line in ann:
            _, position, surface = line.split("\t")
            _, start, end = position.split()
            assert docs["nested/a.txt"].decode()[int(start) : int(end)] == surface
        rows = list(csv.DictReader(io.StringIO(z.read("annotations.tsv").decode()), delimiter="\t"))
        assert list(rows[0])[:5] == ["filename", "label", "start_span", "end_span", "text"]
        assert rows[0]["submitter_email"] == "a@example.org"
        assert "a@example.org" not in "\n".join(ann)
        assert json.loads(z.read("manifest.json"))["job_id"] == "id"
