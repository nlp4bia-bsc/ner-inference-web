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
