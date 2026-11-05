"""Inference orchestration: validate, predict, measure and publish private artifacts."""

import json
import shutil
import time

from app.config import Settings
from app.services.export import package
from app.services.inference import NerLabAdapter, merge_predictions
from app.services.registry import Registry
from app.services.statistics import statistics
from app.storage import LocalStorage
from app.visualization.repository import write_index


def process_job(
    job: dict, s: Settings, adapter=None, stats_fn=statistics, registry_factory=Registry
):
    storage = LocalStorage(s.storage_root)
    root = storage.job(job["id"])
    payload = json.loads(job["payload"])
    registry = registry_factory(s)
    models = registry.select(payload["language"], payload["entities"])
    if [
        {
            k: m.get(k)
            for k in (
                "model_id",
                "version",
                "model_dir",
                "checkpoint_sha256",
                "min_score",
                "batch_size",
            )
        }
        for m in models
    ] != payload["selected_models"]:
        raise ValueError(
            "Model registry changed since admission; resubmit under current configuration"
        )
    raw = {name: (root / "input" / name).read_bytes() for name in payload["documents"]}
    documents = {name: data.decode("utf-8") for name, data in raw.items()}
    temp = root / "building"
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir()
    batches, provenance = [], []
    started = time.monotonic()
    for i, model in enumerate(models):
        rows, meta = (adapter or NerLabAdapter()).predict(
            model, documents, temp / f"model-{i}", s.device
        )
        batches.append((model, rows))
        provenance.append(meta)
    spans = merge_predictions(documents, batches)
    # One explicit reference tokenizer; model-specific subword counts are never summed.
    tokenizer = (
        registry.languages[payload["language"]].get("statistics_model") or models[0]["model_dir"]
    )
    stats, per_doc = stats_fn(documents, spans, payload["language"], tokenizer)
    stats["operational"].update(
        seconds=time.monotonic() - started,
        successful_documents=len(documents),
        failed_documents=0,
        models=provenance,
    )
    manifest = {
        "job_id": job["id"],
        "created_at": job["created_at"],
        "submitter_name": payload["submitter_name"],
        "submitter_email": payload["submitter_email"],
        "language": payload["language"],
        "entities": payload["entities"],
        "documents": payload["documents"],
        "models": provenance,
        "ner_lab_commit": "8640d4797b081a5f6b66d9b45c11269542a79a26",
        "offsets": "Unicode code points; inclusive start, exclusive end",
        "filename_convention": "original relative path including .txt",
        "evaluation": "Not computed: no gold standard provided",
    }
    package(temp / "output", raw, spans, payload, stats, per_doc, manifest)
    write_index(temp / "viewer", raw, spans, per_doc)
    shutil.rmtree(root / "viewer", ignore_errors=True)
    (temp / "viewer").rename(root / "viewer")
    final = root / "output"
    shutil.rmtree(final, ignore_errors=True)
    (temp / "output").rename(final)
    shutil.rmtree(temp)
    return stats["operational"]
