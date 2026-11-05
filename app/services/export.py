import csv
import json
import zipfile
from pathlib import Path

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
]


def write_tsv(path: Path, columns: list[str], rows: list[dict]):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, columns, delimiter="\t", extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


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
    brat = output / "brat"
    brat.mkdir()
    grouped = {name: [] for name in documents}
    for span in spans:
        grouped[span["filename"]].append(span)
    for name, data in documents.items():
        # Original names live beneath documents/, avoiding config filename collisions.
        txt = brat / "documents" / name
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_bytes(data)
        lines = []
        for index, row in enumerate(grouped[name], 1):
            # BRAT surface form is single-line; offsets always refer to unchanged TXT.
            surface = row["text"].replace("\r", " ").replace("\n", " ").replace("\t", " ")
            lines.append(
                f"T{index}\t{row['label']} {row['start_span']} {row['end_span']}\t{surface}\n"
            )
        txt.with_suffix(".ann").write_text("".join(lines), encoding="utf-8")
    (brat / "annotation.conf").write_text(
        "[entities]\n"
        + "\n".join(sorted(payload["entities"]))
        + "\n[relations]\n[events]\n[attributes]\n"
    )
    rows = [
        {**row, **{k: payload[k] for k in ("language", "submitter_name", "submitter_email")}}
        for row in spans
    ]
    write_tsv(output / "annotations.tsv", COLUMNS, rows)
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
