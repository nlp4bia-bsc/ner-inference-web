import json
import time

from app.auth.service import audit, public_user
from app.auth.sessions import require_live
from app.errors import ServiceError
from app.permissions.policies import document_limit, require_admin
from app.services.document_management import retained_count


class AdminService:
    def __init__(self, db, settings, jobs, auth):
        self.db, self.s, self.jobs, self.auth = db, settings, jobs, auth

    def users(self, q="", offset=0, approval=None):
        actor = require_admin()
        query = "%" + q.lower() + "%"
        with self.db.connect() as c:
            require_live(c, actor, self.s, admin=True)
            rows = c.execute(
                "SELECT * FROM users WHERE (lower(full_name) LIKE ? OR lower(email) LIKE ? OR lower(institution) LIKE ? OR id LIKE ?) AND (? IS NULL OR approval_status=?) ORDER BY created_at LIMIT 100 OFFSET ?",
                (query, query, query, query, approval, approval, offset),
            ).fetchall()
            return [
                {
                    **public_user(row, self.s),
                    "occupied_documents": retained_count(c, row["id"], time.time()),
                    "retained_limit": document_limit(
                        row["access_tier"], override=row["document_limit"]
                    ),
                }
                for row in rows
            ]

    def change(self, identity, changes):
        actor = require_admin()
        data = {
            k: v
            for k, v in changes.model_dump(exclude_unset=True).items()
            if v is not None or k == "document_limit"
        }
        if not data:
            raise ServiceError("invalid_form", 422)
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            require_live(c, actor, self.s, admin=True)
            row = c.execute("SELECT * FROM users WHERE id=?", (identity,)).fetchone()
            if not row:
                raise ServiceError("Not found", 404)
            if row["approval_status"] == "DELETING":
                raise ServiceError("account_deleting", 409)
            data = {key: value for key, value in data.items() if row[key] != value}
            if not data:
                return
            if (
                row["system_role"] == "ADMIN"
                and row["account_status"] == "ACTIVE"
                and row["approval_status"] == "APPROVED"
                and (data.get("system_role") == "USER" or data.get("account_status") == "SUSPENDED")
            ):
                if (
                    c.execute(
                        "SELECT count(*) FROM users WHERE system_role='ADMIN' AND account_status='ACTIVE' AND approval_status='APPROVED'"
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

    def review(self, identity, decision):
        actor = require_admin()
        if decision not in ("APPROVED", "REJECTED"):
            raise ServiceError("invalid_form", 422)
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            require_live(c, actor, self.s, admin=True)
            row = c.execute("SELECT * FROM users WHERE id=?", (identity,)).fetchone()
            if not row:
                raise ServiceError("Not found", 404)
            if row["approval_status"] != "PENDING":
                raise ServiceError("approval_reviewed", 409)
            c.execute(
                "UPDATE users SET approval_status=?,approval_reviewed_at=?,approval_reviewed_by=?,updated_at=?,auth_version=auth_version+1 WHERE id=?",
                (decision, time.time(), actor["id"], time.time(), identity),
            )
            self.auth.revoke(c, identity)
            audit(c, actor["id"], identity, "ADMIN_ACCESS_" + decision)

    def projects(self, q="", offset=0):
        actor = require_admin()
        query = "%" + q.lower() + "%"
        with self.db.connect() as c:
            require_live(c, actor, self.s, admin=True)
            rows = c.execute(
                """SELECT j.id,j.status,j.document_count,j.processed_documents,j.created_at,j.expires_at,
              COALESCE(NULLIF(json_extract(j.payload,'$.job_name'),''),json_extract(j.payload,'$.documents[0]'),j.id) AS name,
              json_extract(j.payload,'$.language') AS language,
              u.full_name AS owner_name,u.email AS owner_email,u.institution
              FROM jobs j LEFT JOIN users u ON u.id=j.owner_user_id
              WHERE j.status!='DELETED' AND (lower(COALESCE(u.full_name,'')) LIKE ? OR lower(COALESCE(u.email,'')) LIKE ?
              OR lower(COALESCE(u.institution,'')) LIKE ? OR lower(COALESCE(json_extract(j.payload,'$.job_name'),'')) LIKE ? OR j.id LIKE ?)
              ORDER BY j.seq DESC LIMIT 100 OFFSET ?""",
                (query, query, query, query, query, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_project(self, identity):
        actor = require_admin()
        from app.admin.erasure import erase_project

        return erase_project(self.jobs, identity, actor)

    def delete_account(self, identity, confirm_email):
        from app.admin.erasure import erase_account

        return erase_account(self, identity, confirm_email)

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
                "pending_accounts": c.execute(
                    "SELECT count(*) FROM users WHERE approval_status='PENDING'"
                ).fetchone()[0],
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
