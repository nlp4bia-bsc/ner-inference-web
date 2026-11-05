"""Run one supervised worker. flock prevents a second instance, including recovery races."""

import fcntl
import json
import logging
import multiprocessing
import os
import shutil
import time

from app.config import Settings
from app.db import Database
from app.services.cleanup import cleanup
from app.services.export import package
from app.services.inference import NerLabAdapter, merge_predictions
from app.services.registry import Registry
from app.services.statistics import statistics
from app.storage import LocalStorage

log = logging.getLogger("temu.worker")


def process_job(job: dict, s: Settings, adapter=None, stats_fn=statistics):
    storage = LocalStorage(s.storage_root)
    root = storage.job(job["id"])
    payload = json.loads(job["payload"])
    registry = Registry(s)
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
    final = root / "output"
    shutil.rmtree(final, ignore_errors=True)
    (temp / "output").rename(final)
    shutil.rmtree(temp)
    return stats["operational"]


def child(job: dict, settings_dict: dict, parent_pid: int):
    # Linux production: terminate inference if the supervising worker is killed.
    import ctypes
    import signal

    libc = ctypes.CDLL(None)
    if libc.prctl(1, signal.SIGKILL) != 0 or os.getppid() != parent_pid:
        raise SystemExit("Worker supervision unavailable")
    try:
        settings = Settings(**settings_dict)
        summary = process_job(job, settings)
        # Disk-backed IPC cannot deadlock on a finite pipe buffer for many models.
        path = settings.storage_root / "jobs" / job["id"] / "worker-summary.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(summary, allow_nan=False), encoding="utf-8")
        temp.replace(path)
    except Exception as exc:
        # No exception strings: they can contain patient text, names or private paths.
        log.error("job_failed job_id=%s error_type=%s", job["id"], type(exc).__name__)
        raise SystemExit(1) from None


def execute(job: dict, settings: Settings, db: Database, storage: LocalStorage, target=child):
    """Supervise the entire child lifetime, including result publication and shutdown."""
    path = storage.job(job["id"]) / "worker-summary.json"
    path.unlink(missing_ok=True)  # An interrupted attempt must not reuse stale success.
    path.with_suffix(".tmp").unlink(missing_ok=True)
    context = multiprocessing.get_context("spawn")
    process = context.Process(target=target, args=(job, settings.model_dump(), os.getpid()))
    process.start()
    deadline = time.monotonic() + settings.job_timeout_seconds
    timed_out = False
    try:
        while process.is_alive():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            process.join(min(1, remaining))
            db.heartbeat()
            cleanup(db, storage)
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
        process.join()
    try:
        if timed_out or process.exitcode != 0 or not path.is_file():
            return False, None
        summary = json.loads(path.read_text(encoding="utf-8"))
        return (True, summary) if isinstance(summary, dict) else (False, None)
    except (OSError, ValueError):
        return False, None
    finally:
        path.unlink(missing_ok=True)
        path.with_suffix(".tmp").unlink(missing_ok=True)


def run():
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = Settings()
    storage, db = LocalStorage(s.storage_root), Database(s)
    with (s.storage_root / "worker.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another worker is already active") from None
        db.recover()
        while True:
            db.heartbeat()
            cleanup(db, storage)
            job = db.claim()
            if not job:
                time.sleep(1)
                continue
            ok, summary = execute(job, s, db, storage)
            if not ok:
                shutil.rmtree(storage.job(job["id"]) / "building", ignore_errors=True)
                shutil.rmtree(storage.job(job["id"]) / "output", ignore_errors=True)
            db.finish(job["id"], summary, failed=not ok)


if __name__ == "__main__":
    run()
