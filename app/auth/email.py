"""Encrypted durable email outbox; test capture is never a public endpoint."""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage

from cryptography.fernet import Fernet

from app.errors import ServiceError


def cipher(db, purpose):
    key = hmac.new(db.rate_key, purpose.encode(), hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


class Mailer:
    def __init__(self, settings, db):
        self.s, self.db = settings, db
        self.outbox = []
        self.crypt = cipher(db, "email-outbox-v1")

    @property
    def configured(self):
        return not (
            self.s.mail_backend == "none"
            or (
                self.s.mail_backend == "smtp"
                and (not self.s.smtp_host or not self.s.smtp_from or not self.s.smtp_starttls)
            )
        )

    def require_configured(self):
        if not self.configured:
            raise ServiceError("mail_unavailable", 503)

    def queue(self, recipient, subject, body, expires_at):
        self.require_configured()
        data = self.crypt.encrypt(
            json.dumps({"to": recipient, "subject": subject, "body": body}).encode()
        ).decode()
        with self.db.connect() as c:
            c.execute(
                "INSERT INTO mail_outbox(id,payload,created_at,expires_at,next_attempt) VALUES (?,?,?,?,?)",
                (secrets.token_hex(16), data, time.time(), expires_at, time.time()),
            )

    def flush(self):
        for _ in range(10):
            now = time.time()
            with self.db.connect() as c:
                c.execute("BEGIN IMMEDIATE")
                row = c.execute(
                    "SELECT * FROM mail_outbox WHERE status IN ('PENDING','SENDING') AND next_attempt<=? AND expires_at>? AND attempts<5 ORDER BY created_at LIMIT 1",
                    (now, now),
                ).fetchone()
                if not row:
                    return
                c.execute(
                    "UPDATE mail_outbox SET status='SENDING',attempts=attempts+1,next_attempt=? WHERE id=?",
                    (now + 60, row["id"]),
                )
            try:
                message = json.loads(self.crypt.decrypt(row["payload"].encode()))
                self._deliver(message)
            except Exception as exc:
                logging.getLogger("temu.email").error(
                    "email_delivery_failed error_type=%s", type(exc).__name__
                )
                with self.db.connect() as c:
                    c.execute(
                        "UPDATE mail_outbox SET status='PENDING',next_attempt=? WHERE id=?",
                        (now + 60, row["id"]),
                    )
                continue
            with self.db.connect() as c:
                c.execute(
                    "UPDATE mail_outbox SET status='SENT',payload='' WHERE id=?", (row["id"],)
                )

    def _deliver(self, message):
        if self.s.mail_backend == "memory":
            self.outbox.append(message)
        elif self.s.mail_backend == "file":
            directory = self.s.storage_root / "test-mail"
            directory.mkdir(mode=0o700, exist_ok=True)
            path = directory / (secrets.token_hex(16) + ".json")
            path.write_text(json.dumps(message), encoding="utf-8")
            path.chmod(0o600)
        elif self.s.mail_backend == "smtp":
            mail = EmailMessage()
            mail["From"], mail["To"], mail["Subject"] = (
                self.s.smtp_from,
                message["to"],
                message["subject"],
            )
            mail.set_content(message["body"])
            with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=10) as client:
                client.starttls(context=ssl.create_default_context())
                if self.s.smtp_username:
                    client.login(self.s.smtp_username, self.s.smtp_password.get_secret_value())
                client.send_message(mail)
        else:
            raise ServiceError("mail_unavailable", 503)
