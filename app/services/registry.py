"""Local-only model registry. A successful offline preflight enables a checkpoint."""

import hashlib
import json
import re
from pathlib import Path

import yaml

from app.config import Settings
from app.errors import ServiceError

LABEL = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file())
    if not files:
        raise ValueError("Empty model directory")
    for p in files:
        digest.update(str(p.relative_to(path)).encode())
        with p.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def inspect_checkpoint(entity: dict, language: str, label: str) -> dict:
    path = Path(entity["model_dir"]).resolve()
    data = json.loads((path / "encoding.json").read_text())
    encoding = data["encoding"]
    if encoding.get("language") != language or encoding.get("target_label") != label:
        raise ValueError("Checkpoint language/target_label differs from registry")
    if not any((path / p).is_file() for p in ("model.safetensors", "pytorch_model.bin")):
        raise ValueError("Checkpoint has no supported weights")
    if not (path / "tokenizer.json").is_file():
        raise ValueError("A saved local fast tokenizer is required")
    if not data.get("model") or not encoding.get("label2id"):
        raise ValueError("Incomplete encoding.json")
    return data


class Registry:
    def __init__(self, settings: Settings):
        self.s = settings
        self.languages = yaml.safe_load(settings.model_config_path.read_text())["languages"]
        receipts = (
            json.loads(settings.model_validation_path.read_text())
            if settings.model_validation_path.exists()
            else {}
        )
        for code, language in self.languages.items():
            if not re.fullmatch("[a-z]{2}", code):
                raise ValueError("Language keys must be ISO 639-1 codes")
            for label, e in language["entities"].items():
                if not LABEL.fullmatch(label) or not LABEL.fullmatch(e["model_id"]):
                    raise ValueError("Unsafe label or model ID")
                if not 0 <= e.get("min_score", 0) <= 1 or not 1 <= e.get("batch_size", 16) <= 1024:
                    raise ValueError("Invalid inference options")
                e["available"] = False
                e["checkpoint_sha256"] = None
                if e.get("enabled") and e.get("model_dir"):
                    try:
                        inspect_checkpoint(e, code, label)
                        receipt = receipts.get(f"{code}:{label}", {})
                        e["checkpoint_sha256"] = receipt.get("sha256")
                        e["available"] = (
                            receipt.get("sha256") == fingerprint(Path(e["model_dir"]))
                            and receipt.get("model_id") == e["model_id"]
                        )
                    except (OSError, ValueError, KeyError, TypeError):
                        pass

    def public(self, language: str | None = None) -> list[dict]:
        rows = []
        for code, lang in self.languages.items():
            if language is not None and language != code:
                continue
            for label, e in lang["entities"].items():
                rows.append(
                    {
                        "language": code,
                        "entity": label,
                        "display_name": e["display_name"],
                        "description": e.get("description", ""),
                        "model_id": e["model_id"],
                        "version": e.get("version"),
                        "available": e["available"],
                    }
                )
        return rows

    def select(self, language: str, entities: list[str]) -> list[dict]:
        if language not in self.languages or not entities or len(set(entities)) != len(entities):
            raise ServiceError("Choose a language and one or more available entity types.")
        result = []
        for label in entities:
            e = self.languages[language]["entities"].get(label)
            if not e or not e["available"]:
                raise ServiceError("An entity is not available for this language.")
            result.append({**e, "label": label, "language": language})
        return result
