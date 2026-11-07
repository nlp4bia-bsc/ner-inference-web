"""BRAT originals and stand-off spans, with explicit overlap policy."""

from pathlib import Path

from app.domain.annotations import validate_surface


def write_brat(output: Path, documents: dict[str, bytes], spans: list[dict], payload: dict):
    brat = output / "brat"
    brat.mkdir()
    grouped = {name: [] for name in documents}
    for span in spans:
        validate_surface(
            documents[span["filename"]].decode("utf-8"),
            span["start_span"],
            span["end_span"],
            span["text"],
        )
        grouped[span["filename"]].append(span)
    for name, data in documents.items():
        # Original names live beneath documents/, avoiding config filename collisions.
        txt = brat / "documents" / name
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_bytes(data)
        txt.with_suffix(".ann").write_text(annotation_text(grouped[name]), encoding="utf-8")
    (brat / "annotation.conf").write_text(
        "[entities]\n"
        + "\n".join(sorted(payload["entities"]))
        + "\n[relations]\n<OVERLAP> Arg1:<ANY>, Arg2:<ANY>, <OVL-TYPE>:<ANY>\n[events]\n[attributes]\n"
    )


def annotation_text(spans):
    lines = []
    reference_index = 0
    for index, row in enumerate(spans, 1):
        surface = row["text"].replace("\r", " ").replace("\n", " ").replace("\t", " ")
        lines.append(f"T{index}\t{row['label']} {row['start_span']} {row['end_span']}\t{surface}\n")
        normalized = row.get("normalization")
        if normalized:
            import re

            references = normalized.get("references") or [
                {
                    "code_system": normalized.get("code_system") or "Terminology",
                    "code": normalized["code"],
                }
            ]
            term = normalized["term"].replace("\t", " ").replace("\r", " ").replace("\n", " ")
            seen = set()
            for reference in references:
                system = re.sub(r"[^A-Za-z0-9_.-]", "_", reference["code_system"])
                code = reference["code"]
                if (system, code) in seen:
                    continue
                seen.add((system, code))
                reference_index += 1
                lines.append(f"N{reference_index}\tReference T{index} {system}:{code}\t{term}\n")

    return "".join(lines)
