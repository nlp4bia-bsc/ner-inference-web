import json
import time

from app.auth.service import audit, public_user
from app.auth.sessions import require_live
from app.errors import ServiceError
from app.permissions.policies import require_admin


class AdminService:
    def __init__(self, db, settings):
        self.db, self.s = db, settings

    def users(self, q="", offset=0):
        require_admin()
        query = "%" + q.lower() + "%"
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT * FROM users WHERE lower(email) LIKE ? OR lower(institution) LIKE ? ORDER BY created_at LIMIT 100 OFFSET ?",
                (query, query, offset),
            ).fetchall()
        return [public_user(row, self.s) for row in rows]

    def change(self, identity, changes):
        actor = require_admin()
        data = {k: v for k, v in changes.model_dump().items() if v is not None}
        if not data:
            raise ServiceError("invalid_form", 422)
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            require_live(c, actor, self.s, admin=True)
            row = c.execute("SELECT * FROM users WHERE id=?", (identity,)).fetchone()
            if not row:
                raise ServiceError("Not found", 404)
            data = {key: value for key, value in data.items() if row[key] != value}
            if not data:
                return
            if (
                row["system_role"] == "ADMIN"
                and row["account_status"] == "ACTIVE"
                and (data.get("system_role") == "USER" or data.get("account_status") == "SUSPENDED")
            ):
                if (
                    c.execute(
                        "SELECT count(*) FROM users WHERE system_role='ADMIN' AND account_status='ACTIVE'"
                    ).fetchone()[0]
                    <= 1
                ):
                    raise ServiceError("last_admin", 409)
            for key, value in data.items():
                c.execute(
                    # identifier comes from fixed internal allowlist; all data is bound
                    f"UPDATE users SET {key}=?,updated_at=? WHERE id=?",  # nosec B608
                    (value, time.time(), identity),
                )
            if "account_status" in data or "system_role" in data:
                c.execute("UPDATE users SET auth_version=auth_version+1 WHERE id=?", (identity,))
                c.execute(
                    "UPDATE sessions SET revoked_at=? WHERE user_id=?", (time.time(), identity)
                )
            audit(
                c,
                actor["id"],
                identity,
                "ADMIN_ACCOUNT_CHANGED",
                {key: {"before": row[key], "after": value} for key, value in data.items()},
            )

    def revoke(self, identity):
        actor = require_admin()
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            require_live(c, actor, self.s, admin=True)
            if not c.execute("SELECT 1 FROM users WHERE id=?", (identity,)).fetchone():
                raise ServiceError("Not found", 404)
            c.execute("UPDATE users SET auth_version=auth_version+1 WHERE id=?", (identity,))
            c.execute("UPDATE sessions SET revoked_at=? WHERE user_id=?", (time.time(), identity))
            audit(c, actor["id"], identity, "ADMIN_SESSIONS_REVOKED")

    def metrics(self):
        require_admin()
        with self.db.connect() as c:
            return {
                "accounts": c.execute("SELECT count(*) FROM users").fetchone()[0],
                "jobs_by_status": dict(
                    c.execute("SELECT status,count(*) FROM jobs GROUP BY status").fetchall()
                ),
                "storage_bytes": c.execute(
                    "SELECT COALESCE(sum(storage_bytes),0) FROM jobs"
                ).fetchone()[0],
                "failed_mail": c.execute(
                    "SELECT count(*) FROM mail_outbox WHERE attempts>=5 AND status!='SENT'"
                ).fetchone()[0],
            }

    def history(self, offset=0):
        require_admin()
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT * FROM audit_events WHERE action LIKE 'ADMIN_%' OR action='ACCOUNT_DELETION_REQUESTED' ORDER BY id DESC LIMIT 100 OFFSET ?",
                (offset,),
            ).fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]
