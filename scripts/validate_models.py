"""Administrator-only offline checkpoint preflight; no public model-loading endpoint."""

import json
import os
from pathlib import Path

from app.config import Settings
from app.services.registry import fingerprint, inspect_checkpoint


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import yaml
    from lab.core import sentence_segmenter
    from lab.ner.encoding.encoder import encoder_from_description
    from lab.ner.inference.loading import load_model
    from transformers import AutoTokenizer

    settings = Settings()
    catalog = yaml.safe_load(settings.model_config_path.read_text())["languages"]
    receipts = {}
    for language, lang in catalog.items():
        sentence_segmenter(language)
        reference = lang.get("statistics_model")
        if reference:
            if not Path(reference).is_dir():
                raise ValueError("Statistics tokenizer must be a local directory")
            AutoTokenizer.from_pretrained(reference, local_files_only=True, use_fast=True)
        for label, entity in lang["entities"].items():
            if not entity.get("enabled"):
                continue
            inspect_checkpoint(entity, language, label)
            model, tokenizer, description = load_model(entity["model_dir"], device=settings.device)
            encoder_from_description(description["encoding"], tokenizer, require_target_label=False)
            if not tokenizer.is_fast:
                raise ValueError("Fast tokenizer required")
            receipts[f"{language}:{label}"] = {
                "model_id": entity["model_id"],
                "sha256": fingerprint(Path(entity["model_dir"])),
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
