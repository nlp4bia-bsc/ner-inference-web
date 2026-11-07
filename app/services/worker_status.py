"""Processing-service liveness without exposing other users' jobs or server paths."""

import time
from datetime import datetime, timezone

WORKER_HEARTBEAT_SECONDS = 15


def worker_status(database):
    now = time.time()
    with database.connect() as connection:
        row = connection.execute(
            "SELECT value FROM runtime WHERE key='worker_heartbeat'"
        ).fetchone()
        busy = connection.execute("SELECT 1 FROM jobs WHERE status='PROCESSING' LIMIT 1").fetchone()
    seen = float(row[0]) if row else None
    age = max(0, now - seen) if seen else None
    available = age is not None and age <= WORKER_HEARTBEAT_SECONDS
    return {
        "available": available,
        "state": ("busy" if busy else "idle") if available else "unavailable",
        "last_seen_at": datetime.fromtimestamp(seen, timezone.utc).isoformat() if seen else None,
        "age_seconds": round(age, 1) if age is not None else None,
    }
