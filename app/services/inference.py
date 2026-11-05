"""Real adapter only; tests inject a controlled predictor, never exposed via configuration."""

import math
import os
from pathlib import Path
from time import monotonic


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
            if not 0 <= start < end <= len(text) or text[start:end] != row["text"]:
                raise ValueError("Prediction offsets do not round-trip")
            score = row.get("score")
            if score is not None and (not math.isfinite(float(score)) or not 0 <= score <= 1):
                raise ValueError("Invalid confidence")
            item = {
                **row,
                "start_span": start,
                "end_span": end,
                "score": score,
                "model_id": model["model_id"],
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
