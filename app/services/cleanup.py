import shutil
import time

from app.db import Database
from app.storage import LocalStorage


def cleanup(db: Database, storage: LocalStorage):
    from app.services.normalization import NormalizationCache

    NormalizationCache(db.s).sweep()
    now = time.time()
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        rows = c.execute(
            "SELECT id FROM jobs WHERE status IN ('COMPLETED','COMPLETED_WITH_ERRORS','FAILED','EXPIRED','DELETED') AND expires_at<=?",
            (now,),
        ).fetchall()
        for row in rows:
            c.execute(
                "UPDATE upload_ledger SET state='EXPIRED',removed_at=COALESCE(removed_at,?) WHERE job_id=? AND state='STORED'",
                (now, row["id"]),
            )
            # Delete before commit; failures are retried next sweep, never falsely marked clean.
            storage.delete(row["id"])
            c.execute(
                """UPDATE jobs SET status=CASE WHEN status='DELETED' THEN 'DELETED' ELSE 'EXPIRED' END,payload='{}',summary=NULL,
                         error_summary=NULL,storage_bytes=0,reserved_bytes=0,expired_at=COALESCE(expired_at,?) WHERE id=?""",
                (now, row["id"]),
            )
            c.execute("DELETE FROM documents WHERE job_id=?", (row["id"],))
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
        c.execute(
            "DELETE FROM documents WHERE job_id IN (SELECT id FROM jobs WHERE expired_at<?)", (old,)
        )
        c.execute("DELETE FROM jobs WHERE expired_at<?", (old,))
        c.execute("DELETE FROM limits WHERE accepted_at<?", (now - db.s.rate_limit_seconds,))
        # Upload middleware has a hard 5 minute body timeout. Lease sweep after 10 minutes.
        c.execute("DELETE FROM uploads WHERE created_at<?", (now - 600,))
        for table in ("sessions", "email_verifications", "password_resets"):
            # identifier comes from fixed internal allowlist; all data is bound
            c.execute(f"DELETE FROM {table} WHERE expires_at<?", (now - 86400,))  # nosec B608
        c.execute("DELETE FROM mfa_setups WHERE expires_at<?", (now,))
        c.execute(
            "DELETE FROM auth_limits WHERE window_start<?", (now - db.s.auth_rate_window_seconds,)
        )
        c.execute(
            "DELETE FROM mail_outbox WHERE expires_at<? OR (status='SENT' AND created_at<?)",
            (now, now - 86400),
        )
        c.execute("DELETE FROM audit_events WHERE at<?", (now - db.s.audit_retention_days * 86400,))
        registered = {r[0] for r in c.execute("SELECT id FROM jobs")}
        registered.update(
            r[0] for r in c.execute("SELECT staging_id FROM uploads WHERE staging_id IS NOT NULL")
        )
    for base in (storage.root / "staging", storage.root / "jobs"):
        for path in base.iterdir():
            if path.is_dir() and path.name not in registered and path.stat().st_mtime < now - 600:
                shutil.rmtree(path)
