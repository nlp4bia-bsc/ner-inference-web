"""Atomic, immutable all-model document publication and verified restart reuse."""

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

from app.domain.annotations import canonical_annotations


def read_publication(root: Path, row: dict, snapshot: list):
    path = root / "published" / row["document_id"] / "artifact.json"
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    data = (root / "input" / row["filename"]).read_bytes()
    if record["snapshot"] != snapshot or record["input_sha256"] != hashlib.sha256(data).hexdigest():
        return None
    canonical_annotations(row["document_id"], data.decode("utf-8"), record["spans"])
    return record


def publish(root, row, raw, spans, stats, snapshot, provenance, budget=None):
    from app.services.exports.brat import annotation_text

    parent = root / "published"
    parent.mkdir(exist_ok=True)
    destination = parent / row["document_id"]
    temp = parent / (row["document_id"] + ".building")
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir()
    canonical = canonical_annotations(row["document_id"], raw.decode("utf-8"), spans)
    record = {
        "filename": row["filename"],
        "snapshot": snapshot,
        "spans": spans,
        "annotations": [a.model_dump() for a in canonical],
        "statistics": stats,
        "models": provenance,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
    }
    serialized = json.dumps(record, ensure_ascii=False, allow_nan=False)
    ann = annotation_text(spans)
    if budget:
        budget.write_text(temp / "artifact.json", serialized)
        budget.write_text(temp / "document.ann", ann)
    else:
        (temp / "artifact.json").write_text(serialized, encoding="utf-8")
        (temp / "document.ann").write_text(ann, encoding="utf-8")
    if destination.exists():
        shutil.rmtree(destination)
    temp.rename(destination)
    return len(canonical), dict(Counter(a.label for a in canonical))
