"""Deterministic additional terminology identifiers; primary retrieval codes stay intact."""

import json


def merge_reference_values(values):
    references = set()
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        for row in json.loads(value):
            references.add((row["code_system"], row["code"]))
    return json.dumps(
        [{"code_system": system, "code": code} for system, code in sorted(references)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
