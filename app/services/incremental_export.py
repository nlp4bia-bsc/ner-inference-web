"""Stream final or explicitly partial exports from immutable document publications."""

import csv
import json
import shutil
import time
import zipfile

from app.services.export import COLUMNS, annotation_row
from app.services.exports.tsv import write_tsv


def package_publications(root, rows, payload, stats, manifest, budget=None):
    export_started = time.monotonic()
    output = root / "building" / "output"
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    brat = output / "brat"
    brat.mkdir()
    (brat / "annotation.conf").write_text(
        "[entities]\n"
        + "\n".join(payload["entities"])
        + "\n[relations]\n<OVERLAP> Arg1:<ANY>, Arg2:<ANY>, <OVL-TYPE>:<ANY>\n[events]\n[attributes]\n"
    )
    doc_stats = []
    with (output / "annotations.tsv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, COLUMNS, delimiter="\t", lineterminator="\n", extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            if row["status"] != "ANNOTATED":
                doc_stats.append({"filename": row["filename"], "processing_status": row["status"]})
                continue
            folder = root / "published" / row["document_id"]
            record = json.loads((folder / "artifact.json").read_text(encoding="utf-8"))
            text = brat / "documents" / row["filename"]
            text.parent.mkdir(parents=True, exist_ok=True)
            (budget.copy if budget else shutil.copyfile)(root / "input" / row["filename"], text)
            (budget.copy if budget else shutil.copyfile)(
                folder / "document.ann", text.with_suffix(".ann")
            )
            for span in record["spans"]:
                record_row = annotation_row(
                    {
                        **span,
                        **{
                            k: payload[k] for k in ("language", "submitter_name", "submitter_email")
                        },
                    }
                )
                if budget:
                    import io

                    buffer = io.StringIO(newline="")
                    csv.DictWriter(
                        buffer, COLUMNS, delimiter="\t", lineterminator="\n", extrasaction="ignore"
                    ).writerow(record_row)
                    budget.claim(len(buffer.getvalue().encode("utf-8")))
                writer.writerow(record_row)
            doc_stats.append(record["statistics"])
    if budget:
        budget.claim(sum(len(json.dumps(row).encode("utf-8")) for row in doc_stats) + 4096)
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
        doc_stats,
    )
    for name, value in [("statistics.json", stats), ("manifest.json", manifest)]:
        if budget:
            budget.claim(
                len(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")) + 1024
            )
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8"
        )
    if budget:
        budget.claim(
            sum(int(p.stat().st_size * 1.01) + 1024 for p in output.rglob("*") if p.is_file())
        )
    zip_started = time.monotonic()
    with zipfile.ZipFile(output / "results.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "results.zip":
                archive.write(path, path.relative_to(output))
    shutil.rmtree(root / "output", ignore_errors=True)
    output.rename(root / "output")
    return {
        "zip_seconds": time.monotonic() - zip_started,
        "export_seconds": time.monotonic() - export_started,
    }
