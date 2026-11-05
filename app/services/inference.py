"""Real adapter only; tests inject a controlled predictor, never exposed via configuration."""

import math
import os
from pathlib import Path
from time import monotonic

from app.domain.annotations import validate_surface


def merge_predictions(
    documents: dict[str, str], batches: list[tuple[dict, list[dict]]]
) -> list[dict]:
    spans = {}
    for model, rows in batches:
        for row in rows:
            filename, label = str(row["filename"]), str(row["label"])
            start, end = row["start_span"], row["end_span"]
            if label != model["label"]:
                raise ValueError("Unexpected prediction label")
            if filename not in documents or int(start) != start or int(end) != end:
                raise ValueError("Unknown document or non-integer offset")
            start, end = int(start), int(end)
            text = documents[filename]
            validate_surface(text, start, end, row["text"])
            score = row.get("score")
            if score is not None and (not math.isfinite(float(score)) or not 0 <= score <= 1):
                raise ValueError("Invalid confidence")
            item = {
                **row,
                "start_span": start,
                "end_span": end,
                "score": score,
                "model_id": model["model_id"],
                "model_version": model.get("version"),
            }
            key = (filename, label, start, end)
            if key not in spans or (score if score is not None else -1) > (
                spans[key]["score"] if spans[key]["score"] is not None else -1
            ):
                spans[key] = item
    return [spans[key] for key in sorted(spans, key=lambda k: (k[0], k[2], k[3], k[1]))]


class NerLabAdapter:
    def predict(self, model: dict, documents: dict[str, str], output: Path, device: str):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from lab.ner import predict_entities

        started = monotonic()
        result = predict_entities(
            model_dir=model["model_dir"],
            documents=documents,
            output_dir=output,
            batch_size=model.get("batch_size", 16),
            device=device,
            min_score=model.get("min_score", 0.0),
        )
        # Only expose audited manifest fields; ner_lab's manifest includes private paths.
        provenance = {
            k: result.manifest[k]
            for k in ("model", "encoding", "n_documents", "n_windows", "min_score")
        }
        provenance.update(
            model_id=model["model_id"],
            version=model.get("version"),
            checkpoint_sha256=model.get("checkpoint_sha256"),
            language=model["language"],
            entity=model["label"],
            seconds=monotonic() - started,
            batch_size=model.get("batch_size", 16),
            device=device,
        )
        # Encoding's base_model may be an internal path; keep only configuration, not locations.
        provenance["model"] = {k: v for k, v in provenance["model"].items() if k != "base_model"}
        return result.spans.to_dict("records"), provenance


class NerLabSession:
    """Bounded job-scoped cache using the exact upstream inference building blocks."""

    def __init__(self, max_models=2):
        from collections import OrderedDict

        self.cache = OrderedDict()
        self.max_models = max_models
        self.timings = []

    def predict(self, model, documents, output, device):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from lab.ner.encoding.encoder import encoder_from_description
        from lab.ner.inference.io import read_documents
        from lab.ner.inference.loading import load_model
        from lab.ner.inference.prediction import decode_spans, predict_logits

        key = (model["model_dir"], model.get("checkpoint_sha256"), device)
        started = monotonic()
        loaded = key not in self.cache
        if loaded:
            while len(self.cache) >= self.max_models:
                _, old = self.cache.popitem(last=False)
                del old
            self.cache[key] = load_model(model["model_dir"], device=device)
        self.cache.move_to_end(key)
        weights, tokenizer, description = self.cache[key]
        load_seconds = monotonic() - started
        encoder = encoder_from_description(
            description["encoding"], tokenizer, require_target_label=False
        )
        corpus = read_documents(documents)
        encode_start = monotonic()
        rows = encoder.encode(corpus)
        if rows.empty:
            raise ValueError("No inference windows")
        encoded = monotonic() - encode_start
        infer_start = monotonic()
        logits = predict_logits(
            model=weights,
            tokenizer=tokenizer,
            rows=rows,
            batch_size=model.get("batch_size", 16),
            device=device,
            pad_to_multiple_of=8,
        )
        infer_seconds = monotonic() - infer_start
        decode_start = monotonic()
        spans = decode_spans(
            rows=rows,
            predictions=logits,
            tokenizer=tokenizer,
            id2label=encoder.id2label,
            texts=documents,
            min_score=model.get("min_score", 0.0),
        )
        meta = {
            "model_id": model["model_id"],
            "version": model.get("version"),
            "checkpoint_sha256": model.get("checkpoint_sha256"),
            "language": model["language"],
            "entity": model["label"],
            "encoding": description["encoding"],
            "model": {k: v for k, v in description["model"].items() if k != "base_model"},
            "n_documents": len(documents),
            "n_windows": len(rows),
            "device": device,
            "min_score": model.get("min_score", 0),
            "batch_size": model.get("batch_size", 16),
            "seconds": monotonic() - started,
            "load_seconds": load_seconds,
            "checkpoint_loaded": loaded,
            "encoding_seconds": encoded,
            "inference_seconds": infer_seconds,
            "decoding_seconds": monotonic() - decode_start,
        }
        self.timings.append(meta)
        return spans.to_dict("records"), meta

    def close(self):
        self.cache.clear()
        import gc

        gc.collect()
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
