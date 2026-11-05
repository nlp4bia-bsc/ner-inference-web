import shutil
import time

from app.db import Database
from app.storage import LocalStorage


def cleanup(db: Database, storage: LocalStorage):
    now = time.time()
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        rows = c.execute(
            "SELECT id FROM jobs WHERE status IN ('COMPLETED','FAILED','EXPIRED') AND expires_at<=?",
            (now,),
        ).fetchall()
        for row in rows:
            # Delete before commit; failures are retried next sweep, never falsely marked clean.
            storage.delete(row["id"])
            c.execute(
                """UPDATE jobs SET status='EXPIRED',payload='{}',summary=NULL,
                         error_summary=NULL,expired_at=COALESCE(expired_at,?) WHERE id=?""",
                (now, row["id"]),
            )
            if (
                c.execute(
                    "SELECT count(*) FROM events WHERE job_id=? AND status='EXPIRED'", (row["id"],)
                ).fetchone()[0]
                == 0
            ):
                db.event(c, row["id"], "EXPIRED", now)
        old = now - db.s.tombstone_hours * 3600
        c.execute(
            "DELETE FROM events WHERE job_id IN (SELECT id FROM jobs WHERE expired_at<?)", (old,)
        )
        c.execute("DELETE FROM jobs WHERE expired_at<?", (old,))
        c.execute("DELETE FROM limits WHERE accepted_at<?", (now - db.s.rate_limit_seconds,))
        # Upload middleware has a hard 5 minute body timeout. Lease sweep after 10 minutes.
        c.execute("DELETE FROM uploads WHERE created_at<?", (now - 600,))
        registered = {r[0] for r in c.execute("SELECT id FROM jobs")}
    for base in (storage.root / "staging", storage.root / "jobs"):
        for path in base.iterdir():
            if path.is_dir() and path.name not in registered and path.stat().st_mtime < now - 600:
                shutil.rmtree(path)
