"""Expand scalar/list terminology cells without guessing ambiguous associations."""

import ast
import json
import re
from itertools import product

from app.domain.normalization_references import merge_reference_values


def cell_values(value):
    import pandas as pd

    if isinstance(value, str):
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                try:
                    value = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    pass  # A literal terminology string may begin with brackets.
    if hasattr(value, "tolist"):
        value = value.tolist()
    entries = value if isinstance(value, (list, tuple)) else [value]
    result = []
    for entry in entries:
        if isinstance(entry, (dict, list, tuple)) or hasattr(entry, "tolist"):
            raise ValueError("Nested terminology values require explicit preprocessing")
        if entry is None or pd.isna(entry):
            result.append(None)
            continue
        text = str(entry).strip()
        result.append(text or None)
    return result


def term_code_pairs(terms, codes, list_pairing=None):
    terms, codes = cell_values(terms), cell_values(codes)
    if not terms or not codes:
        return []
    if len(terms) == 1 or len(codes) == 1 or list_pairing == "all":
        pairs = product(terms, codes)
    elif list_pairing == "aligned" and len(terms) == len(codes):
        pairs = zip(terms, codes, strict=True)
    else:
        raise ValueError(
            "Both term and code contain multiple values. Use --list-pairing aligned "
            "only for corresponding positions, or --list-pairing all only when every "
            "term names every code in the row. No association has been guessed."
        )
    return ((term, code) for term, code in pairs if term is not None and code is not None)


def deduplicate_pairs(frame):
    if "references" in frame.columns:
        return frame.groupby(["term", "code"], sort=False, as_index=False)["references"].agg(
            merge_reference_values
        )
    return frame.drop_duplicates(["term", "code"]).reset_index(drop=True)


def prepare_pairs(part, term, code, list_pairing=None, source_column=None, source_code_column=None):
    import pandas as pd

    extra = [source_column, source_code_column] if source_column and source_code_column else []

    def rows():
        for values in part[[term, code, *extra]].itertuples(index=False, name=None):
            references = []
            if extra:
                for source, identifier in term_code_pairs(values[2], values[3], "aligned"):
                    if re.fullmatch(r"[A-Za-z0-9_.:/-]+", identifier):
                        references.append({"code_system": source, "code": identifier})
                if references and len({c for c in cell_values(values[1]) if c}) > 1:
                    raise ValueError(
                        "Multiple primary codes with source identifiers require explicit preprocessing to preserve their correspondence"
                    )
            serialized = json.dumps(references, ensure_ascii=False, separators=(",", ":"))
            for name, identifier in term_code_pairs(values[0], values[1], list_pairing):
                yield (name, identifier, serialized) if extra else (name, identifier)

    frame = pd.DataFrame(rows(), columns=["term", "code", *(["references"] if extra else [])])
    if not frame.empty:
        frame = frame[frame["code"].str.fullmatch(r"[A-Za-z0-9_.:/-]+")]
    return deduplicate_pairs(frame)
