"""Explicitly adopt the configured retention for unexpired terminal jobs; never revive expired data."""

import time

from app.config import Settings
from app.db import Database


def migrate(db: Database) -> int:
    now = time.time()
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        cursor = c.execute(
            "UPDATE jobs SET expires_at=completed_at+? WHERE status IN ('COMPLETED','FAILED') AND expires_at>? AND completed_at IS NOT NULL",
            (db.s.job_results_ttl_hours * 3600, now),
        )
        return cursor.rowcount


if __name__ == "__main__":
    print(f"Updated retention for {migrate(Database(Settings()))} unexpired terminal jobs.")
