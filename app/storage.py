import shutil
from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def job(self, job_id: str) -> Path: ...
    def delete(self, job_id: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (root / "jobs").mkdir(exist_ok=True, mode=0o700)
        (root / "staging").mkdir(exist_ok=True, mode=0o700)

    def job(self, job_id: str) -> Path:
        return self.root / "jobs" / job_id

    def delete(self, job_id: str) -> None:
        path = self.job(job_id)
        if path.exists():
            shutil.rmtree(path)


def directory_bytes(path: Path) -> int:
    """Logical bytes retained by a private job directory (no model/checkpoint files)."""
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


class StorageBudget:
    """Conservative per-job write bound; filesystem quotas remain the hard OS boundary."""

    def __init__(self, root, limit, min_free_bytes=0):
        self.root, self.limit, self.min_free_bytes = root, limit, min_free_bytes
        self.used = directory_bytes(root)

    def claim(self, size):
        if (
            self.used + size > self.limit
            or shutil.disk_usage(self.root).free < size + self.min_free_bytes
        ):
            raise RuntimeError("Job storage budget exceeded")
        self.used += size

    def write_text(self, path, text):
        data = text.encode("utf-8")
        self.claim(len(data))
        path.write_bytes(data)

    def copy(self, source, destination):
        self.claim(source.stat().st_size)
        shutil.copyfile(source, destination)
