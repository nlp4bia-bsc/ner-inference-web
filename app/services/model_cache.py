"""Lazy Hub snapshots in a persistent cache; listing never imports NLP or downloads."""

import fcntl
import hashlib
import json
import re
import shutil
from pathlib import Path

REPOSITORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ModelPreparationError(ValueError):
    pass


def complete_snapshot(path):
    path = Path(path)
    if not (path / "config.json").is_file():
        return False
    tokenizer = any(
        (path / name).is_file()
        for name in (
            "tokenizer.json",
            "vocab.txt",
            "vocab.json",
            "spiece.model",
            "sentencepiece.bpe.model",
        )
    )
    weights = any((path / name).is_file() for name in ("model.safetensors", "pytorch_model.bin"))
    for name in ("model.safetensors.index.json", "pytorch_model.bin.index.json"):
        if (path / name).is_file():
            try:
                index = json.loads((path / name).read_text())
                files = set(index["weight_map"].values())
                weights = bool(files) and all(
                    not Path(value).is_absolute()
                    and ".." not in Path(value).parts
                    and (path / value).is_file()
                    for value in files
                )
            except (OSError, ValueError, KeyError, TypeError):
                weights = False
    return tokenizer and weights


def cached_snapshot(settings, repository, revision="main"):
    if not repository or not REPOSITORY.fullmatch(repository):
        return None
    root = settings.hub_cache / ("models--" + repository.replace("/", "--"))
    commit = revision
    if not re.fullmatch(r"[a-fA-F0-9]{40}", revision):
        ref = root / "refs" / revision
        if ".." in Path(revision).parts or Path(revision).is_absolute():
            return None
        try:
            commit = ref.read_text().strip()
        except OSError:
            return None
    if not re.fullmatch(r"[a-fA-F0-9]{40}", commit):
        return None
    path = root / "snapshots" / commit
    return path if complete_snapshot(path) else None


class ModelCache:
    def __init__(self, settings, job_root):
        self.s, self.job_root = settings, Path(job_root)
        self.on_progress = None
        self.pins_file = self.job_root / "resolved-models.json"
        self.pins = json.loads(self.pins_file.read_text()) if self.pins_file.exists() else {}

    def prepare(self, model):
        if self.on_progress:
            self.on_progress("CHECKING_CACHE")
        repository = model.get("repository")
        local = model.get("model_dir")
        if local and Path(local).is_dir():
            return {**model, "model_dir": str(Path(local).resolve()), "cache_hit": True}
        if not repository or not REPOSITORY.fullmatch(repository):
            raise ModelPreparationError("No configured model source")
        requested = str(model.get("revision") or "main")
        if Path(requested).is_absolute() or ".." in Path(requested).parts:
            raise ModelPreparationError("Invalid configured model revision")
        pin = self.pins.get(model["model_id"])
        if pin and (pin["repository"] != repository or pin["requested_revision"] != requested):
            raise ModelPreparationError("Pinned model source changed")
        revision = pin["resolved_revision"] if pin else requested
        self.s.hub_cache.mkdir(parents=True, exist_ok=True)
        locks = self.s.hub_cache.parent / "download-locks"
        locks.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256((repository + "@" + revision).encode()).hexdigest()
        with (locks / key).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = cached_snapshot(self.s, repository, revision)
            hit = path is not None
            if path is None:
                if self.on_progress:
                    self.on_progress("DOWNLOADING_MODEL")
                from huggingface_hub import snapshot_download

                options = dict(
                    repo_id=repository,
                    revision=revision,
                    cache_dir=str(self.s.hub_cache),
                    local_files_only=self.s.hf_hub_offline,
                    allow_patterns=[
                        "*.json",
                        "*.safetensors",
                        "pytorch_model*.bin",
                        "*.txt",
                        "*.model",
                        "*.tiktoken",
                    ],
                )
                # Only metadata is inspected at this point. Bytes are fetched
                # from the resulting immutable commit, never a moving branch.
                plan = snapshot_download(**options, dry_run=True)  # nosec B615 -- metadata-only resolution of administrator catalog
                commits = {item.commit_hash for item in plan}
                if len(commits) != 1 or not re.fullmatch(r"[a-fA-F0-9]{40}", next(iter(commits))):
                    raise ModelPreparationError("Snapshot metadata has no immutable revision")
                options["revision"] = next(iter(commits))
                required = sum(item.file_size for item in plan if item.will_download)
                if (
                    shutil.disk_usage(self.s.hub_cache).free
                    < required + self.s.min_free_disk_mb * 1024**2
                ):
                    raise ModelPreparationError("Insufficient space for checkpoint cache")
                path = Path(snapshot_download(**options))  # nosec B615 -- revision was resolved and checked above
                if not complete_snapshot(path):
                    raise ModelPreparationError("Incomplete model snapshot")
            commit = path.name
            if not re.fullmatch(r"[a-fA-F0-9]{40}", commit):
                raise ModelPreparationError("Hub snapshot has no immutable revision")
            if not pin and requested != commit:
                ref = (
                    self.s.hub_cache
                    / ("models--" + repository.replace("/", "--"))
                    / "refs"
                    / requested
                )
                ref.parent.mkdir(parents=True, exist_ok=True)
                ref_temp = ref.with_name(ref.name + ".tmp")
                ref_temp.write_text(commit)
                ref_temp.replace(ref)
            self.pins[model["model_id"]] = {
                "repository": repository,
                "requested_revision": requested,
                "resolved_revision": commit,
            }
            temporary = self.pins_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.pins, indent=2))
            temporary.replace(self.pins_file)
        return {
            **model,
            "model_dir": str(path),
            "resolved_revision": commit,
            "version": model.get("version") or commit,
            "cache_hit": hit,
        }
