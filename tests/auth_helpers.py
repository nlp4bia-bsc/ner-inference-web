"""Synthetic accounts always traverse real registration/verification/login endpoints."""

import re
from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.permissions.policies import principal

PASSWORD = "Synthetic test password 2026!"
DEFAULT_EMAIL = "user@example.org"


def csrf_from(response):
    return re.search(r'name="csrf-token" content="([^"]+)"', response.text).group(1)


def approve_fixture_account(app, email):
    """Trusted synthetic setup only. Real review endpoints are verified separately."""
    with app.state.db.connect() as connection:
        connection.execute(
            "UPDATE users SET approval_status='APPROVED' WHERE email=? AND approval_status='PENDING'",
            (email.lower(),),
        )


def approve_fixture_database(root, email):
    """Approve only in a synthetic browser fixture database, never through a test HTTP route."""
    import sqlite3

    with sqlite3.connect(root / "jobs.sqlite3") as connection:
        connection.execute(
            "UPDATE users SET approval_status='APPROVED' WHERE email=? AND approval_status='PENDING'",
            (email.lower(),),
        )


def authenticate(client, email=DEFAULT_EMAIL, verify=True, register=True):
    app = client.app
    prefix = app.state.settings.app_prefix
    client.headers.pop("X-CSRF-Token", None)
    csrf = csrf_from(client.get(prefix + "/register"))
    if register:
        response = client.post(
            prefix + "/api/auth/register",
            json={
                "full_name": "Synthetic Researcher",
                "email": email,
                "institution": "Synthetic University",
                "professional_role": "RESEARCHER",
                "password": PASSWORD,
                "password_confirmation": PASSWORD,
                "legal_accepted": True,
                "csrf_token": csrf,
            },
        )
        assert response.status_code == 200, response.text
    if verify:
        app.state.mailer.flush()
        messages = app.state.mailer.outbox
        for message in reversed(messages):
            if message["to"] == email and "/verify-email?" in message["body"]:
                raw = parse_qs(urlsplit(message["body"].splitlines()[-1]).query)["token"][0]
                response = client.post(
                    prefix + "/api/auth/verify-email", json={"token": raw, "csrf_token": csrf}
                )
                # Existing fixture accounts may have used this one-use link already.
                assert response.status_code in (200, 422), response.text
                break
    approve_fixture_account(app, email)
    csrf = csrf_from(client.get(prefix + "/login"))
    response = client.post(
        prefix + "/api/auth/login", json={"email": email, "password": PASSWORD, "csrf_token": csrf}
    )
    assert response.status_code == 200, response.text
    session = client.get(prefix + "/api/auth/session")
    assert session.status_code == 200, session.text
    client.headers["X-CSRF-Token"] = session.json()["csrf_token"]
    return session.json()["user"]


class AccountClient(TestClient):
    def __enter__(self):
        result = super().__enter__()
        host = self._transport.client[0] if hasattr(self._transport, "client") else "testclient"
        email = DEFAULT_EMAIL if host == "testclient" else host.replace(".", "-") + "@example.org"
        authenticate(self, email)
        cookie = self.cookies.get(self.app.state.settings.session_cookie)
        self._principal_token = principal.set(self.app.state.auth.resolve(cookie))
        return result

    def __exit__(self, *args):
        principal.reset(self._principal_token)
        return super().__exit__(*args)


@contextmanager
def acting_as(app):
    with AccountClient(app):
        yield


def browser_login(page, base, email=DEFAULT_EMAIL):
    page.goto(base + "/login")
    page.locator("#email").fill(email)
    page.locator("#password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in", exact=True).click()
    page.wait_for_url(base + "/?lang=en")
