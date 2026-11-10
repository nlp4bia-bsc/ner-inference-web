"""Transactional revalidation for security-sensitive writes after delayed bodies."""

import time

from app.errors import ServiceError


def require_live(c, account, settings, admin=False):
    now = time.time()
    row = c.execute(
        "SELECT u.*,s.token_hash session_hash,s.expires_at session_expires_at,s.last_seen_at,s.revoked_at,s.auth_version session_version,s.csrf_seed,s.mfa_verified FROM users u JOIN sessions s ON s.user_id=u.id WHERE u.id=? AND s.token_hash=?",
        (account["id"], account["session_hash"]),
    ).fetchone()
    if (
        not row
        or row["revoked_at"]
        or row["session_expires_at"] <= now
        or now - row["last_seen_at"] >= settings.session_idle_seconds
        or row["auth_version"] != row["session_version"]
        or row["account_status"] != "ACTIVE"
        or row["approval_status"] != "APPROVED"
    ):
        raise ServiceError("authentication_required", 401)
    if admin and (
        (settings.require_email_verification and not row["email_verified_at"])
        or row["system_role"] != "ADMIN"
        or (settings.enable_mfa and (not row["mfa_enabled"] or not row["mfa_verified"]))
    ):
        raise ServiceError("forbidden", 403)
    return dict(row)
