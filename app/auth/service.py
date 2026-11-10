"""Account lifecycle, opaque sessions, one-use tokens and administrative TOTP."""

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid

import pyotp

from app.auth.email import cipher
from app.auth.i18n import translate
from app.auth.passwords import DUMMY_HASH, hash_password, hasher, verify_password
from app.auth.sessions import require_live
from app.errors import ServiceError
from app.permissions.policies import document_limit

PUBLIC_FIELDS = (
    "id",
    "full_name",
    "email",
    "institution",
    "professional_role",
    "professional_role_other",
    "email_verified_at",
    "account_status",
    "approval_status",
    "approval_reviewed_at",
    "document_limit",
    "system_role",
    "access_tier",
    "preferred_locale",
    "created_at",
    "updated_at",
    "mfa_enabled",
)


def public_user(row, settings):
    return {
        **{key: row[key] for key in PUBLIC_FIELDS},
        "max_documents_per_job": document_limit(
            row["access_tier"], settings.max_documents_per_job, override=row["document_limit"]
        ),
    }


def audit(c, actor, target, action, details=None):
    c.execute(
        "INSERT INTO audit_events(actor_user_id,target_user_id,action,at,details) VALUES (?,?,?,?,?)",
        (actor, target, action, time.time(), json.dumps(details or {})),
    )


class AuthService:
    def __init__(self, settings, db, mailer):
        self.s, self.db, self.mailer = settings, db, mailer
        self.mfa_cipher = cipher(db, "mfa-secret-v1")

    def throttle(self, operation, email, ip):
        now = time.time()
        blocked = False
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            for value, maximum in [
                ("ip:" + ip, self.s.auth_rate_ip_attempts),
                ("email:" + email.lower(), self.s.auth_rate_email_attempts),
            ]:
                key = self.db.rate_hash("auth:" + operation + ":" + value)
                row = c.execute("SELECT * FROM auth_limits WHERE key=?", (key,)).fetchone()
                count = (
                    row["attempts"]
                    if row and now - row["window_start"] < self.s.auth_rate_window_seconds
                    else 0
                )
                start = row["window_start"] if count else now
                if count >= maximum:
                    blocked = True
                    break
                c.execute(
                    "INSERT OR REPLACE INTO auth_limits VALUES (?,?,?)", (key, start, count + 1)
                )
        if blocked:
            raise ServiceError("rate_limited", 429, self.s.auth_rate_window_seconds)

    def register(self, form, ip):
        if self.s.require_email_verification:
            self.mailer.require_configured()
        self.throttle("register", form.email, ip)
        with self.db.connect() as c:
            exists = c.execute("SELECT 1 FROM users WHERE email=?", (form.email,)).fetchone()
        if exists:
            if self.s.require_email_verification:
                return
            raise ServiceError("email_registered", 409)
        encoded = hash_password(form.password)
        now, identity = time.time(), uuid.uuid4().hex
        try:
            with self.db.connect() as c:
                c.execute(
                    "INSERT INTO users(id,full_name,email,institution,professional_role,professional_role_other,password_hash,preferred_locale,created_at,updated_at,legal_accepted_at,approval_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,'PENDING')",
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
                audit(c, identity, identity, "REGISTER")
        except sqlite3.IntegrityError:
            with self.db.connect() as c:
                if not c.execute("SELECT 1 FROM users WHERE email=?", (form.email,)).fetchone():
                    raise
            if not self.s.require_email_verification:
                raise ServiceError("email_registered", 409) from None
            return
        if self.s.require_email_verification:
            self.issue("verify", identity)

    def issue(self, kind, identity):
        table = "email_verifications" if kind == "verify" else "password_resets"
        seconds = self.s.verification_seconds if kind == "verify" else self.s.reset_seconds
        raw, now = secrets.token_urlsafe(32), time.time()
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM users WHERE id=?", (identity,)).fetchone()
            if not row or row["account_status"] != "ACTIVE":
                return
            c.execute(
                # identifier comes from fixed internal allowlist; all data is bound
                f"UPDATE {table} SET revoked_at=? WHERE user_id=? AND used_at IS NULL",  # nosec B608
                (now, identity),
            )
            c.execute(
                # identifier comes from fixed internal allowlist; all data is bound
                f"INSERT INTO {table}(token_hash,user_id,created_at,expires_at,auth_version) VALUES (?,?,?,?,?)",  # nosec B608
                (self.db.token_hash(raw), identity, now, now + seconds, row["auth_version"]),
            )
        path = "/verify-email" if kind == "verify" else "/reset-password"
        language = row["preferred_locale"]
        url = self.s.public_base_url.rstrip("/") + path + "?token=" + raw + "&lang=" + language
        self.mailer.queue(
            row["email"],
            translate(kind + "_subject", language),
            translate("email_body", language) + "\n\n" + url,
            now + seconds,
        )

    def email_action(self, kind, email, ip):
        self.mailer.require_configured()
        self.throttle(kind, email, ip)
        with self.db.connect() as c:
            row = c.execute(
                "SELECT id,email_verified_at,account_status FROM users WHERE email=?",
                (email.lower(),),
            ).fetchone()
        if (
            row
            and row["account_status"] == "ACTIVE"
            and (kind == "reset" or not row["email_verified_at"])
        ):
            self.issue(kind, row["id"])

    def consume(self, kind, raw, password=None):
        if len(raw) != 43:
            raise ServiceError("invalid_token", 422)
        table = "email_verifications" if kind == "verify" else "password_resets"
        if password is not None:
            with self.db.connect() as c:
                candidate = c.execute(
                    # identifier comes from fixed internal allowlist; all data is bound
                    f"SELECT t.*,u.auth_version current_version FROM {table} t JOIN users u ON u.id=t.user_id WHERE token_hash=?",  # nosec B608
                    (self.db.token_hash(raw),),
                ).fetchone()
            if (
                not candidate
                or candidate["used_at"]
                or candidate["revoked_at"]
                or candidate["expires_at"] <= time.time()
                or candidate["auth_version"] != candidate["current_version"]
            ):
                raise ServiceError("invalid_token", 422)
        encoded = hash_password(password) if password is not None else None
        now = time.time()
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                # identifier comes from fixed internal allowlist; all data is bound
                f"SELECT t.*,u.auth_version current_version FROM {table} t JOIN users u ON u.id=t.user_id WHERE token_hash=?",  # nosec B608
                (self.db.token_hash(raw),),
            ).fetchone()
            if (
                not row
                or row["used_at"]
                or row["revoked_at"]
                or row["expires_at"] <= now
                or row["auth_version"] != row["current_version"]
            ):
                raise ServiceError("invalid_token", 422)
            # identifier comes from fixed internal allowlist; all data is bound
            c.execute(f"UPDATE {table} SET used_at=? WHERE token_hash=?", (now, row["token_hash"]))  # nosec B608
            if kind == "verify":
                c.execute(
                    "UPDATE users SET email_verified_at=COALESCE(email_verified_at,?),updated_at=? WHERE id=?",
                    (now, now, row["user_id"]),
                )
            else:
                c.execute(
                    "UPDATE users SET password_hash=?,auth_version=auth_version+1,updated_at=? WHERE id=?",
                    (encoded, now, row["user_id"]),
                )
                self.revoke(c, row["user_id"])
                c.execute(
                    "UPDATE password_resets SET revoked_at=? WHERE user_id=? AND used_at IS NULL",
                    (now, row["user_id"]),
                )
            audit(
                c,
                row["user_id"],
                row["user_id"],
                "EMAIL_VERIFIED" if kind == "verify" else "PASSWORD_RESET",
            )

    def _new_session(self, c, row, mfa=False, expires=None, csrf_seed=None):
        raw, now = secrets.token_urlsafe(32), time.time()
        c.execute(
            "INSERT INTO sessions(token_hash,user_id,created_at,last_seen_at,expires_at,auth_version,csrf_seed,mfa_verified) VALUES (?,?,?,?,?,?,?,?)",
            (
                self.db.token_hash(raw),
                row["id"],
                now,
                now,
                expires or now + self.s.session_max_seconds,
                row["auth_version"],
                csrf_seed or secrets.token_urlsafe(32),
                int(mfa),
            ),
        )
        return raw

    def login(self, form, ip):
        email = str(form.email).lower()
        self.throttle("login", email, ip)
        with self.db.connect() as c:
            row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        valid = verify_password(row["password_hash"] if row else DUMMY_HASH, form.password)
        if not valid or not row or row["account_status"] != "ACTIVE":
            raise ServiceError("invalid_credentials", 401)
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            live = c.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
            if (
                not live
                or live["password_hash"] != row["password_hash"]
                or live["account_status"] != "ACTIVE"
            ):
                raise ServiceError("invalid_credentials", 401)
            if live["approval_status"] != "APPROVED":
                raise ServiceError(
                    "approval_pending"
                    if live["approval_status"] == "PENDING"
                    else "approval_declined",
                    403,
                )
            if live["mfa_enabled"] and not self._check_mfa(c, live, form.otp):
                raise ServiceError("invalid_credentials", 401)
            if hasher.check_needs_rehash(live["password_hash"]):
                c.execute(
                    "UPDATE users SET password_hash=? WHERE id=?",
                    (hash_password(form.password), live["id"]),
                )
            token = self._new_session(c, live, bool(live["mfa_enabled"]))
            audit(c, live["id"], live["id"], "LOGIN")
        return token

    def resolve(self, token, touch=True):
        if not token or len(token) != 43:
            return None
        now = time.time()
        with self.db.connect() as c:
            row = c.execute(
                "SELECT u.*,s.token_hash session_hash,s.expires_at session_expires_at,s.last_seen_at,s.revoked_at,s.auth_version session_version,s.csrf_seed,s.mfa_verified FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
                (self.db.token_hash(token),),
            ).fetchone()
            if (
                not row
                or row["revoked_at"]
                or row["session_expires_at"] <= now
                or now - row["last_seen_at"] >= self.s.session_idle_seconds
                or row["auth_version"] != row["session_version"]
                or row["account_status"] != "ACTIVE"
                or row["approval_status"] != "APPROVED"
            ):
                return None
            if touch and now - row["last_seen_at"] >= 15:
                c.execute(
                    "UPDATE sessions SET last_seen_at=? WHERE token_hash=? AND revoked_at IS NULL",
                    (now, row["session_hash"]),
                )
            return {**dict(row), "email_verification_required": self.s.require_email_verification}

    def csrf(self, seed):
        return hmac.new(self.db.rate_key, ("csrf:" + seed).encode(), hashlib.sha256).hexdigest()

    def logout(self, account, everywhere=False):
        with self.db.connect() as c:
            if everywhere:
                c.execute(
                    "UPDATE users SET auth_version=auth_version+1 WHERE id=?", (account["id"],)
                )
                self.revoke(c, account["id"])
            else:
                c.execute(
                    "UPDATE sessions SET revoked_at=? WHERE token_hash=?",
                    (time.time(), account["session_hash"]),
                )
            audit(c, account["id"], account["id"], "LOGOUT_ALL" if everywhere else "LOGOUT")

    @staticmethod
    def revoke(c, identity):
        c.execute(
            "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
            (time.time(), identity),
        )

    def rotate(self, account):
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            account = require_live(c, account, self.s)
            c.execute(
                "UPDATE sessions SET revoked_at=? WHERE token_hash=?",
                (time.time(), account["session_hash"]),
            )
            return self._new_session(
                c,
                account,
                account["mfa_verified"],
                account["session_expires_at"],
                account["csrf_seed"],
            )

    def change_password(self, account, form, ip):
        self.throttle("password-change", account["email"], ip)
        if not verify_password(account["password_hash"], form.current_password):
            raise ServiceError("invalid_credentials", 401)
        encoded = hash_password(form.password)
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            require_live(c, account, self.s)
            updated = c.execute(
                "UPDATE users SET password_hash=?,auth_version=auth_version+1,updated_at=? WHERE id=? AND auth_version=?",
                (encoded, time.time(), account["id"], account["auth_version"]),
            )
            if not updated.rowcount:
                raise ServiceError("authentication_required", 401)
            self.revoke(c, account["id"])
            c.execute(
                "UPDATE password_resets SET revoked_at=? WHERE user_id=? AND used_at IS NULL",
                (time.time(), account["id"]),
            )
            audit(c, account["id"], account["id"], "PASSWORD_CHANGED")

    def profile(self, account, form):
        data = form.model_dump()
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            require_live(c, account, self.s)
            c.execute(
                "UPDATE users SET full_name=?,institution=?,professional_role=?,professional_role_other=?,preferred_locale=?,updated_at=? WHERE id=?",
                (
                    data["full_name"],
                    data["institution"],
                    data["professional_role"],
                    data["professional_role_other"],
                    data["preferred_locale"],
                    time.time(),
                    account["id"],
                ),
            )
            audit(c, account["id"], account["id"], "PROFILE_UPDATED")

    def start_mfa(self, account, password, ip):
        self.throttle("mfa", account["email"], ip)
        if account["mfa_enabled"] or not verify_password(account["password_hash"], password):
            raise ServiceError("invalid_credentials", 401)
        secret = pyotp.random_base32()
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            require_live(c, account, self.s)
            c.execute(
                "INSERT OR REPLACE INTO mfa_setups VALUES (?,?,?)",
                (
                    account["id"],
                    self.mfa_cipher.encrypt(secret.encode()).decode(),
                    time.time() + 600,
                ),
            )
        return secret

    def confirm_mfa(self, account, otp, ip):
        self.throttle("mfa-confirm", account["email"], ip)
        codes = [secrets.token_hex(12) for _ in range(8)]
        with self.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            require_live(c, account, self.s)
            row = c.execute("SELECT * FROM mfa_setups WHERE user_id=?", (account["id"],)).fetchone()
            if not row or row["expires_at"] <= time.time():
                raise ServiceError("invalid_token", 422)
            secret = self.mfa_cipher.decrypt(row["secret"].encode()).decode()
            totp = pyotp.TOTP(secret)
            counter = int(time.time() // 30)
            matched = next(
                (
                    counter + offset
                    for offset in (-1, 0, 1)
                    if hmac.compare_digest(totp.at((counter + offset) * 30), otp)
                ),
                None,
            )
            if matched is None:
                raise ServiceError("invalid_credentials", 401)
            hashes = [self.db.rate_hash("recovery:" + code) for code in codes]
            c.execute(
                "UPDATE users SET mfa_secret=?,mfa_enabled=1,mfa_last_counter=?,mfa_recovery_hashes=? WHERE id=? AND mfa_enabled=0",
                (row["secret"], matched, json.dumps(hashes), account["id"]),
            )
            c.execute("DELETE FROM mfa_setups WHERE user_id=?", (account["id"],))
            self.revoke(c, account["id"])
            audit(c, account["id"], account["id"], "MFA_ENABLED")
        return codes

    def _check_mfa(self, c, account, value):
        if not value or not value.isascii():
            return False
        secret = self.mfa_cipher.decrypt(account["mfa_secret"].encode()).decode()
        totp = pyotp.TOTP(secret)
        now = time.time()
        for offset in (-1, 0, 1):
            counter = int(now // 30) + offset
            if counter > account["mfa_last_counter"] and hmac.compare_digest(
                totp.at(counter * 30), value
            ):
                c.execute(
                    "UPDATE users SET mfa_last_counter=? WHERE id=?", (counter, account["id"])
                )
                return True
        hashes = json.loads(account["mfa_recovery_hashes"])
        wanted = self.db.rate_hash("recovery:" + value)
        match = next((item for item in hashes if hmac.compare_digest(item, wanted)), None)
        if match:
            hashes.remove(match)
            c.execute(
                "UPDATE users SET mfa_recovery_hashes=? WHERE id=?",
                (json.dumps(hashes), account["id"]),
            )
            audit(c, account["id"], account["id"], "MFA_RECOVERY_USED")
            return True
        return False
