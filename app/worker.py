"""Run one supervised worker. flock prevents a second instance, including recovery races."""

import fcntl
import json
import logging
import multiprocessing
import os
import shutil
import sys
import time

from app.config import Settings
from app.db import Database
from app.persistence.job_locks import JobContentChanged, check_content_version, job_lock
from app.services import pipeline
from app.services.cleanup import cleanup
from app.services.registry import Registry
from app.services.runtime import inference_dependencies
from app.services.statistics import statistics
from app.storage import LocalStorage

log = logging.getLogger("temu.worker")


def process_job(job: dict, s: Settings, adapter=None, stats_fn=statistics):
    return pipeline.process_job(
        job, s, adapter=adapter, stats_fn=stats_fn, registry_factory=Registry
    )


def child(job: dict, settings_dict: dict, parent_pid: int):
    # Linux production: terminate inference if the supervising worker is killed.
    import ctypes
    import signal

    libc = ctypes.CDLL(None)
    if libc.prctl(1, signal.SIGKILL) != 0 or os.getppid() != parent_pid:
        raise SystemExit("Worker supervision unavailable")
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("temu").setLevel(logging.INFO)
    try:
        # Scientific children do not need email credentials or .env parsing.
        for name in tuple(os.environ):
            if name.startswith("SMTP_"):
                os.environ.pop(name, None)
        settings = Settings(**settings_dict, _env_file=None)
        summary = process_job(job, settings)
        # Disk-backed IPC cannot deadlock on a finite pipe buffer for many models.
        path = settings.storage_root / "jobs" / job["id"] / "worker-summary.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(summary, allow_nan=False), encoding="utf-8")
        temp.replace(path)
    except Exception as exc:
        # No exception strings: they can contain patient text, names or private paths.
        from app.persistence.model_progress import ModelProgressRepository

        try:
            ModelProgressRepository.interrupt(
                Database(Settings(**settings_dict, _env_file=None)), job, type(exc).__name__
            )
        except Exception:
            log.error("progress_unavailable job_id=%s", job["id"])
        log.error("job_failed job_id=%s error_type=%s", job["id"], type(exc).__name__)
        raise SystemExit(1) from None


def execute(job: dict, settings: Settings, db: Database, storage: LocalStorage, target=child):
    """Supervise the entire child lifetime, including result publication and shutdown."""
    path = storage.job(job["id"]) / "worker-summary.json"
    path.unlink(missing_ok=True)  # An interrupted attempt must not reuse stale success.
    path.with_suffix(".tmp").unlink(missing_ok=True)
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=target,
        args=(
            job,
            {
                **settings.model_dump(
                    exclude={
                        name for name in type(settings).model_fields if name.startswith("smtp_")
                    }
                ),
                "mail_backend": "none",
            },
            os.getpid(),
        ),
    )
    process.start()
    deadline = time.monotonic() + settings.job_timeout_seconds
    timed_out = False
    content_changed = False
    try:
        while process.is_alive():
            try:
                check_content_version(db, job)
            except JobContentChanged:
                content_changed = True
                break
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
            reason = (
                "JobTimeout"
                if timed_out
                else "ContentChanged"
                if content_changed
                else "WorkerInterrupted"
            )
            log.error(
                "job_interrupted job_id=%s reason=%s exit_code=%s timeout_seconds=%s",
                job["id"],
                reason,
                process.exitcode,
                settings.job_timeout_seconds,
            )
            if not content_changed:
                from app.persistence.model_progress import ModelProgressRepository

                ModelProgressRepository.interrupt(db, job, reason)
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
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("temu").setLevel(logging.INFO)
    s = Settings()
    missing = [name for name, present in inference_dependencies().items() if not present]
    if missing:
        log.error(
            "worker_runtime_unavailable missing_modules=%s python=%s",
            ",".join(missing),
            sys.executable,
        )
        raise SystemExit(
            "Install inference libraries in this Python environment: "
            "python3 -m pip install -r requirements-cpu.lock (CPU) "
            "or requirements-nlp.lock (GPU). No jobs were claimed."
        )
    storage, db = LocalStorage(s.storage_root), Database(s)
    with (s.storage_root / "worker.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another worker is already active") from None
        db.recover()
        log.info(
            "worker_ready python=%s database=%s loading_mode=%s waiting_for_jobs=true",
            sys.executable,
            s.db_path.resolve(),
            s.model_loading_mode,
        )
        while True:
            db.heartbeat()
            cleanup(db, storage)
            job = db.claim()
            if not job:
                time.sleep(1)
                continue
            log.info("job_started job_id=%s documents=%s", job["id"], job["document_count"])
            ok, summary = execute(job, s, db, storage)
            if not ok:
                from app.persistence.model_progress import ModelProgressRepository

                # execute records timeout/exit details; do not overwrite that reason.
                ModelProgressRepository.interrupt(db, job, "WorkerInterrupted")
                with job_lock(s, job["id"]):
                    shutil.rmtree(storage.job(job["id"]) / "building", ignore_errors=True)
                    shutil.rmtree(storage.job(job["id"]) / "output", ignore_errors=True)
            db.finish(
                job["id"], summary, failed=not ok, claimed_version=job.get("content_version", 0)
            )
            log.info("job_finished job_id=%s success=%s", job["id"], ok)


if __name__ == "__main__":
    run()
