"""Short filesystem critical sections shared by publication and user deletion."""

import fcntl
from contextlib import contextmanager


class JobContentChanged(RuntimeError):
    pass


@contextmanager
def job_lock(settings, identity):
    directory = settings.storage_root / "job-locks"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / (identity + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def check_content_version(database, job):
    with database.connect() as connection:
        current = connection.execute(
            "SELECT status,content_version FROM jobs WHERE id=?", (job["id"],)
        ).fetchone()
    if (
        not current
        or current["status"] in ("DELETED", "EXPIRED")
        or current["content_version"] != job.get("content_version", 0)
    ):
        raise JobContentChanged("Document set changed")
