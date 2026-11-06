"""Configured model choices; availability is independent of cache or loaded weights."""

import hashlib
import json
import re
from pathlib import Path

import yaml

from app.config import Settings
from app.errors import ServiceError

LABEL = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
SNAPSHOT_FIELDS = (
    "model_id",
    "version",
    "model_dir",
    "checkpoint_sha256",
    "min_score",
    "batch_size",
)
CATALOG_FIELDS = (
    "label",
    "language",
    "target_label",
    "label_mapping",
    "task",
    "requires",
    "languages",
)


def model_snapshot(models, *, legacy=False):
    fields = SNAPSHOT_FIELDS if legacy else SNAPSHOT_FIELDS + CATALOG_FIELDS
    return [
        {
            k: m.get(k)
            for k in (
                *fields,
                *(("repository", "revision") if m.get("repository") and not legacy else ()),
            )
        }
        for m in models
    ]


def model_contract(model):
    return {k: model.get(k) for k in CATALOG_FIELDS}


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
    target = entity.get("target_label", label)
    if encoding.get("language") != language or encoding.get("target_label") != target:
        raise ValueError("Checkpoint language/target_label differs from registry")
    # The pinned native encoder represents one target per checkpoint. Multi-label
    # or dependent classifiers need their own audited native adapter, never guessing.
    if entity.get("task", "ner") != "ner" or entity.get("requires"):
        raise ValueError("This task requires an audited dependency-aware adapter")
    mapping = entity.get("label_mapping", {target: label})
    if set(mapping) != {target} or set(encoding.get("label2id", {})) != {
        "O",
        f"B-{target}",
        f"I-{target}",
    }:
        raise ValueError("Label schema is not supported by the pinned native encoder")
    if not any((path / p).is_file() for p in ("model.safetensors", "pytorch_model.bin")):
        raise ValueError("Checkpoint has no supported weights")
    if not (path / "tokenizer.json").is_file():
        raise ValueError("A saved local fast tokenizer is required")
    if not data.get("model"):
        raise ValueError("Incomplete encoding.json")
    return data


class Registry:
    def __init__(self, settings: Settings):
        self.s = settings
        catalog = yaml.safe_load(settings.model_config_path.read_text())
        self.languages = catalog["languages"]
        self.multilingual = catalog.get("multilingual", {"entities": {}})
        self.models = {}
        self.bindings = []
        definitions = catalog.get("models", {})
        receipts = (
            json.loads(settings.model_validation_path.read_text())
            if settings.model_validation_path.exists()
            else {}
        )
        for code in self.languages:
            if not re.fullmatch("[a-z]{2}", code):
                raise ValueError("Language keys must be ISO 639-1 codes")
        scopes = [*self.languages.items(), ("mul", self.multilingual)]
        for code, language in scopes:
            for label, category in language["entities"].items():
                if not LABEL.fullmatch(label):
                    raise ValueError("Unsafe canonical category")
                entries = category.get("models")
                if entries is None:
                    entries = []
                if "model_id" in category:
                    entries = [category, *entries]
                for entry in entries:
                    legacy = isinstance(entry, dict)
                    e = entry if legacy else {**definitions[entry], "model_id": entry}
                    identity = e["model_id"]
                    if not LABEL.fullmatch(identity):
                        raise ValueError("Unsafe model ID")
                    if (
                        not 0 <= e.get("min_score", 0) <= 1
                        or not 1 <= e.get("batch_size", 16) <= 1024
                    ):
                        raise ValueError("Invalid inference options")
                    target = e.get("target_label", label)
                    mapping = e.get("label_mapping", {target: label})
                    if (
                        not mapping
                        or any(
                            not LABEL.fullmatch(k) or not LABEL.fullmatch(v)
                            for k, v in mapping.items()
                        )
                        or label not in mapping.values()
                    ):
                        raise ValueError("Invalid original-label/canonical-category mapping")
                    e.setdefault("target_label", target)
                    e.setdefault("label_mapping", mapping)
                    e.setdefault("language", code)
                    e.setdefault("task", "ner")
                    e.setdefault("requires", [])
                    if not isinstance(e["requires"], list):
                        raise ValueError("Model dependencies must be a list")
                    supported = e.get(
                        "languages", list(self.languages) if code == "mul" else [code]
                    )
                    if not supported or any(x not in self.languages for x in supported):
                        raise ValueError("Unknown supported language")
                    e["languages"] = supported
                    e["label"] = sorted(mapping.values())[0]
                    e["available"] = False
                    e["checkpoint_sha256"] = None
                    e["unavailable_reason"] = (
                        e.get("unavailable_reason") or "No validated local checkpoint."
                    )
                    if settings.model_loading_mode == "on_demand":
                        from app.services.model_cache import REPOSITORY, cached_snapshot

                        repository = e.get("repository")
                        local = e.get("model_dir")
                        e["available"] = bool(
                            (repository and REPOSITORY.fullmatch(repository))
                            or (local and Path(local).is_dir())
                        )
                        cached = cached_snapshot(
                            settings, repository, str(e.get("revision") or "main")
                        )
                        e["load_state"] = (
                            "local"
                            if local and Path(local).is_dir()
                            else "cached"
                            if cached
                            else "on_demand"
                        )
                        e["unavailable_reason"] = (
                            None
                            if e["available"]
                            else "No model repository or local directory configured."
                        )
                    elif (
                        e["task"] != "ner"
                        or e["requires"]
                        or e.get("schema_review") == "pending"
                        or e.get("dependency_review") == "pending"
                    ):
                        e["unavailable_reason"] = (
                            e.get("unavailable_reason")
                            if e.get("unavailable_reason") != "No validated local checkpoint."
                            else (
                                "Dependency/schema review and an audited pipeline adapter are required."
                            )
                        )
                    elif e.get("enabled") and e.get("model_dir"):
                        try:
                            inspect_checkpoint(e, e["language"], label)
                            receipt = receipts.get(
                                identity, receipts.get(f"{code}:{label}", {}) if legacy else {}
                            )
                            e["checkpoint_sha256"] = receipt.get("sha256")
                            e["available"] = (
                                receipt.get("sha256") == fingerprint(Path(e["model_dir"]))
                                and receipt.get("model_id") == identity
                                and (
                                    receipt.get("contract") == model_contract(e)
                                    or (legacy and "contract" not in receipt)
                                )
                            )
                        except (OSError, ValueError, KeyError, TypeError):
                            pass
                    if identity in self.models:
                        # A shared checkpoint may be referenced from multiple categories/scopes.
                        previous = self.models[identity]
                        if any(
                            previous.get(k) != e.get(k)
                            for k in SNAPSHOT_FIELDS + CATALOG_FIELDS
                            if k != "label"
                        ):
                            raise ValueError("Conflicting definitions for a shared checkpoint")
                        e = previous
                    self.models[identity] = e
                    self.bindings.append((code, label, category, identity))
        for identity, model in self.models.items():
            declared = {label for _, label, _, key in self.bindings if key == identity}
            if set(model["label_mapping"].values()) != declared:
                raise ValueError("Every predicted canonical category must have a catalog binding")
            self._dependency_order([identity])

    def _dependency_order(self, identities):
        ordered, visiting = [], set()

        def visit(identity):
            if identity in visiting:
                raise ValueError("Cyclic model dependency")
            if identity in ordered:
                return
            if identity not in self.models:
                raise ValueError("Unknown model dependency")
            visiting.add(identity)
            for dependency in self.models[identity]["requires"]:
                visit(dependency)
            visiting.remove(identity)
            ordered.append(identity)

        for identity in identities:
            visit(identity)
        return ordered

    def public(self, language: str | None = None) -> list[dict]:
        rows = []
        for code, label, category, identity in self.bindings:
            e = self.models[identity]
            if self.s.model_loading_mode == "on_demand" and e.get("repository"):
                from app.services.model_cache import cached_snapshot

                e["load_state"] = (
                    "cached"
                    if cached_snapshot(self.s, e["repository"], str(e.get("revision") or "main"))
                    else "on_demand"
                )
            if language is not None and (
                code != language and not (code == "mul" and language in e["languages"])
            ):
                continue
            rows.append(
                {
                    "language": code,
                    "entity": label,
                    "display_name": category["display_name"],
                    "description": category.get("description", ""),
                    "model_id": identity,
                    "model_name": e.get("name", identity),
                    "version": e.get("version"),
                    "available": e["available"],
                    "load_state": e.get("load_state", "local" if e["available"] else "unavailable"),
                    "unavailable_reason": None if e["available"] else e["unavailable_reason"],
                    "languages": e["languages"],
                    "task": e["task"],
                    "requires": e["requires"],
                    "repository": e.get("repository"),
                    "metrics": e.get("verified_metrics", {}),
                    "label_mapping": e["label_mapping"],
                }
            )
        # Empty registered categories remain visible; absence of a checkpoint is explicit.
        for code, lang in [*self.languages.items(), ("mul", self.multilingual)]:
            if language is not None and code not in (language, "mul"):
                continue
            for label, category in lang["entities"].items():
                if not any(r["language"] == code and r["entity"] == label for r in rows):
                    rows.append(
                        {
                            "language": code,
                            "entity": label,
                            "display_name": category["display_name"],
                            "description": category.get("description", ""),
                            "model_id": None,
                            "available": False,
                            "unavailable_reason": "No published, validated checkpoint registered.",
                        }
                    )
        return rows

    def select(
        self, language: str, entities: list[str], model_ids: list[str] | None = None
    ) -> list[dict]:
        if language not in self.languages or len(set(entities)) != len(entities):
            raise ServiceError("Choose a language and one or more available models.")
        if model_ids is None:
            if not entities:
                raise ServiceError("Choose one or more available models.")
            model_ids = []
            for label in entities:
                legacy = self.languages[language]["entities"].get(label, {}).get("model_id")
                candidates = (
                    [legacy]
                    if legacy
                    else [
                        identity
                        for code, category, _, identity in self.bindings
                        if code == language and category == label
                    ]
                )
                if len(candidates) != 1:
                    raise ServiceError(
                        "Choose checkpoints explicitly for categories with multiple models."
                    )
                model_ids.extend(candidates)
        if not model_ids or len(set(model_ids)) != len(model_ids):
            raise ServiceError("Choose distinct available checkpoints.")
        allowed = {identity for code, _, _, identity in self.bindings if code in (language, "mul")}
        ordered = self._dependency_order_checked(model_ids)
        result = []
        for identity in ordered:
            e = self.models[identity]
            if identity not in allowed or language not in e["languages"] or not e["available"]:
                raise ServiceError("A checkpoint is unavailable for this language.")
            result.append({**e})
        categories = {label for e in result for label in e["label_mapping"].values()}
        if entities and set(entities) != categories:
            raise ServiceError("Entity categories do not match the selected checkpoints.")
        return result

    def _dependency_order_checked(self, identities):
        try:
            return self._dependency_order(identities)
        except ValueError:
            raise ServiceError("Unknown checkpoint selection.") from None


def statistics_reference(language: dict, models: list[dict]) -> tuple[str | None, str | None]:
    reference = language.get("statistics_model") or models[0].get("model_dir")
    if not reference:
        return None, None
    path = Path(reference).resolve()
    for model in models:
        if (
            model.get("model_dir")
            and Path(model["model_dir"]).resolve() == path
            and model.get("checkpoint_sha256")
        ):
            return str(path), model["checkpoint_sha256"]
    return str(path), fingerprint(path)
