from contextvars import ContextVar

from app.errors import ServiceError

principal: ContextVar[dict | None] = ContextVar("principal", default=None)
TIERS = {"STANDARD": 100, "EXTENDED": 1000, "UNLIMITED": None}


def user():
    account = principal.get()
    if not account:
        raise ServiceError("authentication_required", 401)
    return account


def require_owner(job):
    if job.get("owner_user_id") != user()["id"]:
        raise ServiceError("Request not found.", 404)
    return job


def document_limit(tier, technical=None):
    fixed = TIERS[tier]
    limits = [value for value in (fixed, technical) if value is not None]
    return min(limits) if limits else None


def require_admin():
    account = user()
    if account["system_role"] != "ADMIN":
        raise ServiceError("forbidden", 403)
    if account.get("email_verification_required") and not account.get("email_verified_at"):
        raise ServiceError("verification_required", 403)
    if not account.get("mfa_enabled") or not account.get("mfa_verified"):
        raise ServiceError("mfa_required", 403)
    return account
