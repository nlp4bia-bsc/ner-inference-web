"""Administrator-only offline checkpoint preflight; no public model-loading endpoint."""

import json
import os
from pathlib import Path

from app.config import Settings
from app.services.registry import Registry, fingerprint, inspect_checkpoint, model_contract


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from lab.core import sentence_segmenter
    from lab.ner.encoding.encoder import encoder_from_description
    from lab.ner.inference.loading import load_model
    from transformers import AutoTokenizer

    settings = Settings()
    registry = Registry(settings)
    receipts = {}
    for language, lang in registry.languages.items():
        reference = lang.get("statistics_model")
        if reference:
            if not Path(reference).is_dir():
                raise ValueError("Statistics tokenizer must be a local directory")
            AutoTokenizer.from_pretrained(reference, local_files_only=True, use_fast=True)
    for identity, entity in registry.models.items():
        if not entity.get("enabled"):
            continue
        if entity.get("schema_review") == "pending" or entity.get("dependency_review") == "pending":
            raise ValueError(
                "Complete original-label and dependency review before enabling a checkpoint"
            )
        sentence_segmenter(entity["language"])
        inspect_checkpoint(entity, entity["language"], entity["label"])
        model, tokenizer, description = load_model(entity["model_dir"], device=settings.device)
        encoder_from_description(description["encoding"], tokenizer, require_target_label=False)
        if not tokenizer.is_fast:
            raise ValueError("Fast tokenizer required")
        receipts[identity] = {
            "model_id": identity,
            "sha256": fingerprint(Path(entity["model_dir"])),
            "contract": model_contract(entity),
        }
        del model, tokenizer
    settings.model_validation_path.parent.mkdir(parents=True, exist_ok=True)
    temp = settings.model_validation_path.with_suffix(".tmp")
    temp.write_text(json.dumps(receipts, indent=2))
    temp.chmod(0o644)  # non-secret IDs/digests must be readable by the runtime UID
    temp.replace(settings.model_validation_path)
    print(f"Validated {len(receipts)} local checkpoints; restart API and worker.")


if __name__ == "__main__":
    main()
