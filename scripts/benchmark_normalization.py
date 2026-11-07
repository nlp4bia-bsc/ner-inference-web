"""Synthetic direct-Parquet lookup benchmark; does not read private terminology."""

import json
import platform
import resource
import tempfile
import time
import unicodedata
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from app.services.lexical_normalization import KEY_FORMAT, LexicalMatcher
from app.services.normalization_catalog import file_sha256


def case(size):
    with tempfile.TemporaryDirectory(prefix="ner-lexical-benchmark-") as folder:
        path = Path(folder) / "terms.parquet"
        schema = pa.schema(
            [("term", pa.string()), ("code", pa.string()), ("_match_key", pa.string())]
        )
        with pq.ParquetWriter(path, schema) as writer:
            for start in range(0, size, 8192):
                terms = [
                    f"synthetic clinical procedure {i:07d}"
                    for i in range(start, min(size, start + 8192))
                ]
                codes = [f"C{i % 150000:07d}" for i in range(start, min(size, start + 8192))]
                writer.write_table(
                    pa.table({"term": terms, "code": codes, "_match_key": terms}, schema=schema)
                )
        source = {
            "file": path,
            "sha256": file_sha256(path),
            "lexical_key_format": KEY_FORMAT,
            "lexical_key_unicode": unicodedata.unidata_version,
        }
        started = time.perf_counter()
        matcher = LexicalMatcher(source, lambda *args: None)
        load = time.perf_counter() - started
        exact = [f"synthetic clinical procedure {i:07d}" for i in (0, 13, size // 2, size - 1)]
        fuzzy = [f"synthetic clinical procedure {i:06d}x" for i in (13, size // 3, size - 1)]
        timings = {}
        for name, queries in (("exact", exact), ("fuzzy", fuzzy), ("repeat_fuzzy", fuzzy)):
            started = time.perf_counter()
            rows = matcher.match(queries, "levenshtein", 0.8, 5, lambda *args: None)
            timings[name + "_seconds"] = round(time.perf_counter() - started, 6)
            assert all(rows), "Synthetic query unexpectedly unmatched"
        result = {
            "rows": size,
            "load_seconds": round(load, 6),
            "exact_queries": len(exact),
            "fuzzy_queries": len(fuzzy),
            **timings,
            "process_peak_rss_mib": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
            ),
            "parquet_mib": round(path.stat().st_size / 1024**2, 2),
            **matcher.metadata,
        }
        matcher.close()
        return result


def main():
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "note": "Synthetic lexical lookup only; cumulative process RSS, not a clinical benchmark",
                "results": [case(size) for size in (100_000, 1_000_000)],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
