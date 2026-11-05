"""Private viewer index and per-document readers; no exporter or HTTP dependencies."""

import csv
import fcntl
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from app.domain.annotations import canonical_annotations
from app.errors import ServiceError


def document_id(filename: str) -> str:
    return hashlib.sha256(filename.encode("utf-8")).hexdigest()[:32]


def write_index(
    destination: Path, documents: dict[str, bytes], spans: list[dict], statistics: list[dict]
) -> None:
    destination.mkdir(parents=True)
    grouped = {name: [] for name in documents}
    for span in spans:
        grouped[span["filename"]].append(span)
    stats = {row["filename"]: row for row in statistics}
    index = []
    for filename, data in documents.items():
        identity = document_id(filename)
        rows = canonical_annotations(identity, data.decode("utf-8"), grouped[filename])
        (destination / (identity + ".json")).write_text(
            json.dumps([r.model_dump() for r in rows], ensure_ascii=False, allow_nan=False),
            encoding="utf-8",
        )
        index.append(
            {
                "document_id": identity,
                "filename": filename,
                "annotation_count": len(rows),
                "entities_by_label": dict(Counter(r.label for r in rows)),
                "status": "COMPLETED",
                "statistics": stats.get(filename, {}),
            }
        )
    (destination / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")


class DocumentRepository:
    def __init__(self, jobs):
        self.jobs = jobs

    def root(self, token: str) -> Path:
        job = self.jobs.completed(token)
        root = self.jobs.storage.job(job["id"])
        if not (root / "viewer" / "index.json").is_file():
            self.backfill(root, job)
        return root

    def backfill(self, root: Path, job: dict) -> None:
        # Compatibility with jobs completed by v1, serialized across web processes.
        with (root / "viewer.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if (root / "viewer" / "index.json").is_file():
                return
            with (root / "output" / "annotations.tsv").open(encoding="utf-8", newline="") as f:
                spans = list(csv.DictReader(f, delimiter="\t"))
            for span in spans:
                span["start_span"], span["end_span"] = (
                    int(span["start_span"]),
                    int(span["end_span"]),
                )
                span["score"] = float(span["score"]) if span.get("score") else None
            with (root / "output" / "document_statistics.tsv").open(
                encoding="utf-8", newline=""
            ) as f:
                stats = list(csv.DictReader(f, delimiter="\t"))
            payload = json.loads(job["payload"])
            documents = {
                name: (root / "input" / name).read_bytes() for name in payload["documents"]
            }
            temporary = Path(tempfile.mkdtemp(prefix="viewer-build-", dir=root))
            try:
                write_index(temporary / "viewer", documents, spans, stats)
                (temporary / "viewer").rename(root / "viewer")
            finally:
                shutil.rmtree(temporary)

    def index(self, token: str) -> list[dict]:
        return json.loads((self.root(token) / "viewer" / "index.json").read_text(encoding="utf-8"))

    def document(self, token: str, identity: str) -> tuple[Path, dict]:
        root = self.root(token)
        record = next((row for row in self.index(token) if row["document_id"] == identity), None)
        if record is None:
            raise ServiceError("Document not found.", 404)
        return root, record

    def text(self, token: str, identity: str) -> tuple[dict, str]:
        root, record = self.document(token, identity)
        return record, (root / "input" / record["filename"]).read_bytes().decode("utf-8")

    def annotations(self, token: str, identity: str) -> list[dict]:
        root, _ = self.document(token, identity)
        return json.loads((root / "viewer" / (identity + ".json")).read_text(encoding="utf-8"))
