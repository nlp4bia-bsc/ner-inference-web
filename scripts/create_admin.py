"""Offline institutional bootstrap. Passwords are read from the terminal, never argv."""

import getpass
import sys
import time

from app.auth.email import Mailer
from app.auth.service import AuthService, audit
from app.config import Settings
from app.db import Database
from app.users.schemas import Register


def create_admin(settings, form):
    """Trusted local command; no public bootstrap endpoint or first-registrant rule."""
    db = Database(settings)
    service = AuthService(settings, db, Mailer(settings, db))
    import uuid

    from app.auth.passwords import hash_password

    service.mailer.require_configured()
    encoded = hash_password(form.password)
    identity, now = uuid.uuid4().hex, time.time()
    with db.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute(
            "SELECT 1 FROM users WHERE system_role='ADMIN' OR email=?", (form.email,)
        ).fetchone():
            raise ValueError("Bootstrap requires a new email and no existing administrator")
        c.execute(
            "INSERT INTO users(id,full_name,email,institution,professional_role,professional_role_other,password_hash,preferred_locale,created_at,updated_at,legal_accepted_at,system_role) VALUES (?,?,?,?,?,?,?,?,?,?,?,'ADMIN')",
            (
                identity,
                form.full_name,
                form.email,
                form.institution,
                form.professional_role,
                form.professional_role_other,
                encoded,
                form.preferred_locale,
                now,
                now,
                now,
            ),
        )
        audit(c, identity, identity, "ADMIN_BOOTSTRAP")
    service.issue("verify", identity)
    return identity


def main():
    if not sys.stdin.isatty():
        raise SystemExit(
            "Use an interactive terminal; passwords are never accepted as command arguments."
        )
    settings = Settings()
    full_name = input("Full name: ")
    email = input("Email: ")
    institution = input("Institution: ")
    password = getpass.getpass("Password (15–1024 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    try:
        form = Register(
            full_name=full_name,
            email=email,
            institution=institution,
            professional_role="RESEARCHER",
            password=password,
            password_confirmation=confirmation,
            legal_accepted=True,
        )
        create_admin(settings, form)
        print("Administrator created. Verify email, sign in and enroll MFA before administration.")
    except Exception:
        raise SystemExit(
            "Administrator creation failed. Check configuration, profile and password confirmation; no credentials were printed."
        ) from None


if __name__ == "__main__":
    main()
