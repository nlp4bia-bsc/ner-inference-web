import json
import zipfile
from pathlib import Path

from app.services.exports.brat import write_brat
from app.services.exports.tsv import write_tsv

COLUMNS = [
    "filename",
    "label",
    "start_span",
    "end_span",
    "text",
    "score",
    "language",
    "model_id",
    "submitter_name",
    "submitter_email",
    "model_version",
    "model_ids",
    "original_labels",
    "sources",
]


def annotation_row(row):
    return {
        **row,
        **{
            key: json.dumps(row.get(key, []), ensure_ascii=False, allow_nan=False)
            for key in ("model_ids", "original_labels", "sources")
        },
    }


def package(
    output: Path,
    documents: dict[str, bytes],
    spans: list[dict],
    payload: dict,
    stats: dict,
    document_stats: list[dict],
    manifest: dict,
):
    output.mkdir(parents=True, exist_ok=True)
    write_brat(output, documents, spans, payload)
    rows = [
        {**row, **{k: payload[k] for k in ("language", "submitter_name", "submitter_email")}}
        for row in spans
    ]
    write_tsv(output / "annotations.tsv", COLUMNS, [annotation_row(r) for r in rows])
    write_tsv(
        output / "document_statistics.tsv",
        [
            "filename",
            "characters",
            "words",
            "tokens",
            "sentences",
            "entities_total",
            "processing_status",
        ],
        document_stats,
    )
    for name, value in (("statistics.json", stats), ("manifest.json", manifest)):
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
    with zipfile.ZipFile(output / "results.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "results.zip":
                archive.write(path, path.relative_to(output))
