"""Public encoder priorities and private, locally imported terminology resources."""

import hashlib
import json
import re
from pathlib import Path

import yaml

CATEGORIES = ("MEDICATION", "PROCEDURE", "DISEASE", "SYMPTOM")


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class NormalizationCatalog:
    def __init__(self, settings):
        self.s = settings
        root = settings.normalization_gazetteer_dir.resolve()
        self.root = root
        manifest = root / "manifest.json"
        self.imported = manifest.is_file()
        self.resources = {}
        if manifest.is_file():
            document = json.loads(manifest.read_text())
            for row in document["resources"]:
                if (
                    not re.fullmatch(r"[a-z]{2}", row["language"])
                    or row["entity"] not in CATEGORIES
                ):
                    raise ValueError("Invalid terminology language/category")
                path = root / row["path"]
                if path.suffix != ".parquet" or not path.resolve().is_relative_to(root):
                    raise ValueError(
                        "Terminology file must remain in the private gazetteer directory"
                    )
                self.resources[row["language"], row["entity"]] = {**row, "file": path}
        path = settings.normalization_model_config_path
        self.models = yaml.safe_load(path.read_text())["models"] if path.is_file() else {}

    def resolve(self, language, entity):
        if not self.s.normalization_enabled or entity not in CATEGORIES:
            return None
        for selected in dict.fromkeys((language, "en")):
            row = self.resources.get((selected, entity))
            if row and self.models.get(selected) and row["file"].is_file():
                return {
                    **row,
                    "requested_language": language,
                    "resolved_language": selected,
                    "fallback_to_english": selected != language,
                    "models": self.models[selected],
                }
        return None

    def unavailability_reason(self, language, entity):
        if not self.s.normalization_enabled:
            return "NORMALIZATION_DISABLED"
        if not self.imported:
            return "TERMINOLOGY_NOT_IMPORTED"
        rows = [
            self.resources[key]
            for key in dict.fromkeys(((language, entity), ("en", entity)))
            if key in self.resources
        ]
        if rows and not any(row["file"].is_file() for row in rows):
            return "TERMINOLOGY_FILE_MISSING"
        if any(row["file"].is_file() and not self.models.get(row["language"]) for row in rows):
            return "NORMALIZATION_ENCODER_UNCONFIGURED"
        return "TERMINOLOGY_UNAVAILABLE"

    def snapshot(self, language, entities):
        result = []
        for entity in sorted(set(entities) & set(CATEGORIES)):
            row = self.resolve(language, entity)
            result.append(
                {
                    "entity": entity,
                    "requested_language": language,
                    **(
                        {
                            key: row.get(key)
                            for key in (
                                "sha256",
                                "code_system",
                                "resolved_language",
                                "fallback_to_english",
                                "models",
                            )
                        }
                        if row
                        else {"unavailable": True}
                    ),
                }
            )
        return result

    def public(self, language):
        return {
            "enabled": self.s.normalization_enabled,
            "available": any(self.resolve(language, entity) for entity in CATEGORIES),
            "categories": [
                {
                    "entity": entity,
                    "available": bool(self.resolve(language, entity)),
                    "error_code": None
                    if self.resolve(language, entity)
                    else self.unavailability_reason(language, entity),
                    "language": self.resolve(language, entity)["resolved_language"]
                    if self.resolve(language, entity)
                    else None,
                }
                for entity in CATEGORIES
            ],
            "max_length": 256,
            "index": "FlatIP",
            "cache_languages": self.s.normalization_cache_languages,
            "cache_hours": self.s.normalization_cache_ttl_hours,
        }
