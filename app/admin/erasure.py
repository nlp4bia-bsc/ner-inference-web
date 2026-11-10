"""Administrative erasure: revoke first, fence workers and remove private content."""

import json
import secrets
import time

from cryptography.fernet import InvalidToken

from app.auth.service import audit
from app.auth.sessions import require_live
from app.errors import ServiceError
from app.permissions.policies import require_admin
from app.persistence.job_locks import job_lock


def erase_project(jobs, identity, actor, *, account_id=None):
    """Keep a redacted tombstone so a late worker cannot resurrect an erased job."""
    job = jobs.db.get(identity)
    with job_lock(jobs.settings, job["id"]):
        with jobs.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            require_live(connection, actor, jobs.settings, admin=True)
            current = connection.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()
            if not current or (account_id is not None and current["owner_user_id"] != account_id):
                raise ServiceError("Request not found.", 404)
            jobs.storage.delete(job["id"])
            for table in ("documents", "model_progress", "events"):
                connection.execute(f"DELETE FROM {table} WHERE job_id=?", (job["id"],))  # nosec B608 -- fixed internal table allowlist
            now = time.time()
            connection.execute(
                "UPDATE upload_ledger SET state='DELETED',removed_at=? WHERE job_id=?",
                (now, job["id"]),
            )
            connection.execute(
                """UPDATE jobs SET status='DELETED',stage='DELETED',content_version=content_version+1,
              owner_user_id=NULL,token_hash=?,payload='{}',summary=NULL,error_summary=NULL,
              document_count=0,processed_documents=0,storage_bytes=0,reserved_bytes=0,
              updated_at=?,completed_at=?,expires_at=?,expired_at=? WHERE id=?""",
                (jobs.db.token_hash(secrets.token_urlsafe(32)), now, now, now, now, job["id"]),
            )
            audit(
                connection,
                actor["id"],
                current["owner_user_id"],
                "ADMIN_PROJECT_DELETED",
                {"job_id": job["id"]},
            )
    return {"deleted": True}


def erase_account(service, identity, confirm_email):
    """A failed erasure stays DELETING and can be retried; it never restores access."""
    actor = require_admin()
    if identity == actor["id"]:
        raise ServiceError("delete_self", 409)
    with service.db.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        require_live(connection, actor, service.s, admin=True)
        target = connection.execute("SELECT * FROM users WHERE id=?", (identity,)).fetchone()
        if not target:
            raise ServiceError("Not found", 404)
        if target["email"].lower() != str(confirm_email).lower():
            raise ServiceError("invalid_form", 422)
        if (
            target["system_role"] == "ADMIN"
            and target["account_status"] == "ACTIVE"
            and target["approval_status"] == "APPROVED"
        ):
            count = connection.execute(
                "SELECT count(*) FROM users WHERE system_role='ADMIN' AND account_status='ACTIVE' AND approval_status='APPROVED'"
            ).fetchone()[0]
            if count <= 1:
                raise ServiceError("last_admin", 409)
        connection.execute(
            "UPDATE users SET approval_status='DELETING',account_status='SUSPENDED',auth_version=auth_version+1,updated_at=? WHERE id=?",
            (time.time(), identity),
        )
        service.auth.revoke(connection, identity)
        audit(connection, actor["id"], identity, "ADMIN_ACCOUNT_DELETION_STARTED")
    with service.db.connect() as connection:
        projects = [
            row[0]
            for row in connection.execute("SELECT id FROM jobs WHERE owner_user_id=?", (identity,))
        ]
    for project in projects:
        erase_project(service.jobs, project, actor, account_id=identity)
    with service.db.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        require_live(connection, actor, service.s, admin=True)
        target = connection.execute("SELECT * FROM users WHERE id=?", (identity,)).fetchone()
        if not target or target["approval_status"] != "DELETING":
            raise ServiceError("account_deleting", 409)
        # Admission revalidates the same user row in its write transaction. Once
        # DELETING is committed no new accepted project can appear for this ID.
        if connection.execute(
            "SELECT 1 FROM jobs WHERE owner_user_id=? LIMIT 1", (identity,)
        ).fetchone():
            raise ServiceError("account_deleting", 409)
        for row in connection.execute(
            "SELECT id,payload FROM mail_outbox WHERE payload!=''"
        ).fetchall():
            try:
                message = json.loads(service.auth.mailer.crypt.decrypt(row["payload"].encode()))
            except (InvalidToken, ValueError):
                continue
            if message.get("to", "").lower() == target["email"].lower():
                connection.execute("DELETE FROM mail_outbox WHERE id=?", (row["id"],))
        for table in ("sessions", "email_verifications", "password_resets", "mfa_setups"):
            connection.execute(f"DELETE FROM {table} WHERE user_id=?", (identity,))  # nosec B608 -- fixed internal table allowlist
        connection.execute("DELETE FROM upload_ledger WHERE owner_user_id=?", (identity,))
        connection.execute("DELETE FROM users WHERE id=?", (identity,))
        audit(
            connection, actor["id"], identity, "ADMIN_ACCOUNT_DELETED", {"projects": len(projects)}
        )
    return {"deleted": True, "projects": len(projects)}
