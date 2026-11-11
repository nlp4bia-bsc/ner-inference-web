"""Small, text-free aggregates of canonical annotations and native text metrics."""

import json
import math
from collections import Counter
from functools import lru_cache

COUNTERS = (
    "entities_by_label",
    "annotations_by_model",
    "normalizations_by_label",
    "normalization_methods",
    "normalization_languages",
    "documents_by_language",
    "annotations_by_language",
    "documents_by_model",
    "document_states",
    "job_states",
)
TOTALS = (
    "projects",
    "expired_projects",
    "documents",
    "annotations",
    "normalizations",
    "documents_with_annotations",
    "unavailable_documents",
    "partial_projects",
)
TEXT_METRICS = ("characters", "words", "tokens", "sentences")


def empty_statistics():
    return {
        **dict.fromkeys(TOTALS, 0),
        **{key: {} for key in COUNTERS},
        "text_statistics": dict.fromkeys(TEXT_METRICS),
        "entity_types": 0,
        "models_with_predictions": 0,
        "models_used": 0,
    }


def text_statistics(values):
    """Legacy TSV measurements are strings; unknown/nonfinite values stay unknown."""
    result = {}
    for key in TEXT_METRICS:
        value = values.get(key)
        try:
            value = float(value) if value is not None and not isinstance(value, bool) else None
        except (ValueError, TypeError):
            value = None
        if value is None or not math.isfinite(value) or value < 0:
            result[key] = None
        else:
            result[key] = int(value) if value.is_integer() else value
    return result


def annotation_statistics(annotations):
    """Count mentions once; contributing models can each support the same mention."""
    result = empty_statistics()
    result["annotations"] = len(annotations)
    counters = {key: Counter() for key in COUNTERS}
    for annotation in annotations:
        label = annotation["label"]
        counters["entities_by_label"][label] += 1
        models = set(annotation.get("model_ids") or [])
        models.update(s["model_id"] for s in annotation.get("sources", []) if s.get("model_id"))
        if annotation.get("model_id"):
            models.add(annotation["model_id"])
        counters["annotations_by_model"].update(models)
        normalized = annotation.get("normalization")
        if normalized:
            result["normalizations"] += 1
            counters["normalizations_by_label"][label] += 1
            method = normalized.get("method", "bi_encoder")
            # Match the existing public UI vocabulary, not the implementation name.
            method = {
                "levenshtein": "Fuzzy match",
                "exact": "Exact match",
                "bi_encoder": "Bi-encoder",
            }.get(method, method)
            counters["normalization_methods"][method] += 1
            if normalized.get("language"):
                counters["normalization_languages"][normalized["language"]] += 1
    result.update({key: dict(value) for key, value in counters.items()})
    result["entity_types"] = len(result["entities_by_label"])
    result["models_with_predictions"] = len(result["annotations_by_model"])
    result["documents_by_model"] = dict.fromkeys(result["annotations_by_model"], 1)
    result["models_used"] = len(result["documents_by_model"])
    return result


@lru_cache(maxsize=2048)
def saved_statistics(path, modified_ns, size, inode):
    """Cache only counters, never text/terms; file generation is part of the key."""
    record = json.loads(path.read_text(encoding="utf-8"))
    result = annotation_statistics(record["annotations"] if isinstance(record, dict) else record)
    if isinstance(record, dict):
        models = dict(result["documents_by_model"])
        for model in record.get("models", []):
            if isinstance(model, dict) and model.get("model_id"):
                models[model["model_id"]] = 1
        result["documents_by_model"] = models
        result["models_used"] = len(models)
    return result


def aggregate_statistics(summaries):
    result = empty_statistics()
    counters = {key: Counter() for key in COUNTERS}
    for summary in summaries:
        for key in TOTALS:
            result[key] += summary.get(key, 0)
        for key in COUNTERS:
            counters[key].update(summary.get(key, {}))
        for key in TEXT_METRICS:
            value = summary.get("text_statistics", {}).get(key)
            if value is not None:
                current = result["text_statistics"][key]
                result["text_statistics"][key] = value + (current if current is not None else 0)
    result.update({key: dict(sorted(value.items())) for key, value in counters.items()})
    result["entity_types"] = len(result["entities_by_label"])
    result["models_with_predictions"] = len(result["annotations_by_model"])
    result["models_used"] = len(result["documents_by_model"])
    return result
