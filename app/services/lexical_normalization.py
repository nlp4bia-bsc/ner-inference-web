"""Direct private Parquet lookup with sorted in-memory keys and native edit scoring."""

import bisect
import math
import unicodedata
from collections import OrderedDict

from app.domain.normalization_references import merge_reference_values
from app.services.normalization_catalog import file_sha256

KEY_FORMAT = 1


def normalized_form(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class ArrowKeys:
    """Expose Arrow's sorted string column to Python's binary search without copying."""

    def __init__(self, values):
        self.values = values

    def __len__(self):
        return len(self.values)

    def __getitem__(self, index):
        return self.values[index].as_py()


class LexicalMatcher:
    def __init__(self, resource, report):
        import pyarrow as pa
        import pyarrow.compute as pc
        import pyarrow.parquet as pq

        self.matches = OrderedDict()
        self.reference_cache = {}
        self.pc = pc
        report("READING_TERMINOLOGY")
        if file_sha256(resource["file"]) != resource["sha256"]:
            raise ValueError("Terminology changed since admission")
        schema = pq.read_schema(resource["file"])
        precomputed = (
            resource.get("lexical_key_format") == KEY_FORMAT
            and resource.get("lexical_key_unicode") == unicodedata.unidata_version
            and "_match_key" in schema.names
        )
        columns = [
            "term",
            "code",
            *(["references"] if "references" in schema.names else []),
            *(["_match_key"] if precomputed else []),
        ]
        table = pq.read_table(resource["file"], columns=columns, memory_map=True)
        if not precomputed:
            report("BUILDING_LEXICAL_INDEX", 0, len(table), "pairs")
            chunks = []
            completed = 0
            for batch in table.select(["term"]).to_batches(max_chunksize=8192):
                chunks.append(
                    pa.array(
                        [normalized_form(value or "") for value in batch.column(0).to_pylist()]
                    )
                )
                completed += batch.num_rows
                report("BUILDING_LEXICAL_INDEX", completed, len(table), "pairs")
            table = table.append_column("_match_key", pa.chunked_array(chunks))
            table = table.sort_by(
                [("_match_key", "ascending"), ("code", "ascending"), ("term", "ascending")]
            )
        else:
            report("LOADING_INDEX", len(table), len(table), "pairs")
        self.table = table
        self.keys = ArrowKeys(table["_match_key"].combine_chunks())
        self.forms = pc.unique(table["_match_key"])
        self.lengths = pc.utf8_length(self.forms)
        self.complete_references = precomputed
        self.metadata = {
            "pairs": len(table),
            "normalized_forms": len(self.forms),
            "concepts": int(pc.count_distinct(table["code"]).as_py()),
            "precomputed_keys": precomputed,
            "cache_hit": False,
            "key_normalization": "NFKC-casefold-whitespace",
            "unicode": unicodedata.unidata_version,
        }

    def _records(self, form):
        left = bisect.bisect_left(self.keys, form)
        right = bisect.bisect_right(self.keys, form)
        return self.table.slice(left, right - left).to_pylist()

    def _forms(self, query, threshold, cutoff):
        from rapidfuzz import process
        from rapidfuzz.distance import Levenshtein

        length = len(query)
        minimum = math.ceil(length * threshold - 1e-9)
        maximum = math.floor(length / threshold + 1e-9) if threshold else 2147483647
        selected = self.pc.filter(
            self.forms,
            self.pc.and_(
                self.pc.greater_equal(self.lengths, minimum),
                self.pc.less_equal(self.lengths, maximum),
            ),
        )
        for start in range(0, len(selected), 4096):
            choices = selected.slice(start, 4096).to_pylist()
            lengths = {}
            for form in choices:
                lengths.setdefault(len(form), []).append(form)
            for form_length, group in lengths.items():
                maximum_length = max(length, form_length)
                # An integer distance bound is conservative; the normalized comparison
                # below enforces the exact inclusive threshold without C-float cutoffs.
                maximum_edits = math.ceil((1 - cutoff()) * maximum_length)
                for form, edits, _ in process.extract(
                    query,
                    group,
                    scorer=Levenshtein.distance,
                    score_cutoff=maximum_edits,
                    limit=None,
                ):
                    score = 1 - edits / maximum_length
                    if score >= cutoff():
                        yield form, score

    def match(self, mentions, method, threshold, k, report):
        results = []
        report("MATCHING", 0, len(mentions), "mentions")
        for index, mention in enumerate(mentions, 1):
            query = normalized_form(mention)
            key = (query, method, threshold, k)
            if key in self.matches:
                self.matches.move_to_end(key)
                results.append(self.matches[key])
                report("MATCHING", index, len(mentions), "mentions")
                continue
            candidates = {}

            def cutoff():
                return max(
                    threshold,
                    min(row["score"] for row in candidates.values()) if len(candidates) >= k else 0,
                )

            forms = []
            if query:
                position = bisect.bisect_left(self.keys, query)
                if position < len(self.keys) and self.keys[position] == query:
                    forms = [(query, 1.0)]
                elif method == "levenshtein":
                    forms = self._forms(query, threshold, cutoff)
            for form, score in forms:
                for row in self._records(form):
                    code, term = row["code"], row["term"]
                    previous = candidates.get(code)
                    if (
                        previous is None
                        or score > previous["score"]
                        or (score == previous["score"] and term < previous["term"])
                    ):
                        candidates[code] = {
                            "term": term,
                            "code": code,
                            "score": score,
                            "references": row.get("references") or "[]",
                        }
                    elif score == previous["score"]:
                        previous["references"] = merge_reference_values(
                            [previous["references"], row.get("references") or "[]"]
                        )
                candidates = {
                    row["code"]: row
                    for row in sorted(
                        candidates.values(),
                        key=lambda row: (-row["score"], row["code"], row["term"]),
                    )[:k]
                }
            ranked = sorted(
                candidates.values(), key=lambda row: (-row["score"], row["code"], row["term"])
            )
            if not self.complete_references and "references" in self.table.column_names:
                for row in ranked:
                    if row["code"] not in self.reference_cache:
                        references = self.pc.filter(
                            self.table["references"], self.pc.equal(self.table["code"], row["code"])
                        ).to_pylist()
                        self.reference_cache[row["code"]] = merge_reference_values(references)
                    row["references"] = self.reference_cache[row["code"]]
            self.matches[key] = ranked
            if len(self.matches) > 4096:
                self.matches.popitem(last=False)
            results.append(ranked)
            report("MATCHING", index, len(mentions), "mentions")
        return results

    def close(self):
        self.matches.clear()
        self.reference_cache.clear()
        self.table = self.keys = self.forms = self.lengths = None
