"""Canonical quoted TSV output."""

import csv
from pathlib import Path


def write_tsv(path: Path, columns: list[str], rows: list[dict]):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, columns, delimiter="\t", extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
