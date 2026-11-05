"""Default-deny ASGI gate before body spooling, with live sessions and CSRF."""

import asyncio
import hmac
import json
import re
import sqlite3
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.auth.i18n import locale, translate
from app.errors import ServiceError
from app.permissions.policies import principal, require_owner

AUTH_PAGES = {
    "/login",
    "/register",
    "/verify-email",
    "/resend-verification",
    "/forgot-password",
    "/reset-password",
}
PUBLIC_API = {
    "/api/auth/" + name
    for name in (
        "login",
        "register",
        "verify-email",
        "resend-verification",
        "forgot-password",
        "reset-password",
    )
}
PUBLIC_ASSETS = {
    "/static/auth.css",
    "/static/auth.js",
    "/static/i18n.js",
    "/static/assets/bsc-blue.svg",
}
SAFE = {"GET", "HEAD", "OPTIONS"}


class AuthMiddleware:
    def __init__(self, app, auth):
        self.app, self.auth, self.s = app, auth, auth.s

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.lower(): v.decode("latin-1") for k, v in scope["headers"]}
        cookies = SimpleCookie()
        try:
            cookies.load(headers.get(b"cookie", ""))
        except Exception:
            pass

        def cookie(name):
            return cookies[name].value if name in cookies else ""

        query = parse_qs(scope.get("query_string", b"").decode("utf-8", errors="replace"))
        language = locale(query.get("lang", [cookie("temu_locale") or "en"])[0])
        scope["auth_locale"] = language
        token = principal.set(None)
        scope["security_headers_applied"] = True

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message["headers"] += [
                    (b"cache-control", b"no-store"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-robots-tag", b"noindex, nofollow"),
                    (b"x-content-type-options", b"nosniff"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                    ),
                    (b"vary", b"Cookie"),
                ]
            await send(message)

        try:
            path = scope["path"]
            prefix = self.s.app_prefix
            if prefix and path != prefix and not path.startswith(prefix + "/"):
                return await JSONResponse({"detail": "Not found"}, 404)(scope, receive, secure_send)
            path = path[len(prefix) :] or "/"
            method = scope["method"]
            account = await run_in_threadpool(
                self.auth.resolve,
                cookie(self.s.session_cookie),
                method not in SAFE or not path.startswith(("/api/", "/static/")),
            )
            scope["auth_user"] = account
            if account:
                principal.set(account)
                if "lang" not in query and not cookie("temu_locale"):
                    language = locale(account["preferred_locale"])
                    scope["auth_locale"] = language
            public = (
                (path in AUTH_PAGES and method in ("GET", "HEAD", "POST"))
                or (path in PUBLIC_API and method == "POST")
                or (path in PUBLIC_ASSETS and method in ("GET", "HEAD"))
                or (path in ("/health", "/ready") and method in ("GET", "HEAD"))
            )
            if not public and not account:
                if path.startswith("/api/") or path == "/openapi.json":
                    raise ServiceError("authentication_required", 401)
                return await RedirectResponse(prefix + "/login", 303)(scope, receive, secure_send)
            located = re.match(r"^/(?:api/)?jobs/([^/]+)(?:/|$)", path)
            if prefix and scope["path"] == prefix and method in ("GET", "HEAD"):
                return await RedirectResponse(prefix + "/", 303)(scope, receive, secure_send)
            if located:
                await run_in_threadpool(lambda: require_owner(self.auth.db.get(located.group(1))))
            if method not in SAFE:
                expected_origin = urlsplit(self.s.public_base_url)
                origin = headers.get(b"origin")
                referer = headers.get(b"referer")
                source = urlsplit(origin or referer or "")
                # Chromium navigations under no-referrer may use an opaque Origin.
                # Fetch Metadata must still prove same-origin; the HMAC CSRF check
                # below is mandatory for this case too.
                opaque_same_origin = (
                    origin == "null" and headers.get(b"sec-fetch-site") == "same-origin"
                )
                if (
                    headers.get(b"sec-fetch-site") == "cross-site"
                    or (origin or referer)
                    and not opaque_same_origin
                    and (source.scheme, source.netloc)
                    != (expected_origin.scheme, expected_origin.netloc)
                ):
                    raise ServiceError("csrf_failed", 403)
                public_auth = path in AUTH_PAGES or path in PUBLIC_API
                seed = cookie("temu_challenge") if public_auth else account["csrf_seed"]
                supplied = headers.get(b"x-csrf-token", "")
                if path != "/api/jobs":
                    body = bytearray()
                    deadline = time.monotonic() + 30
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError()
                        message = await asyncio.wait_for(receive(), timeout=remaining)
                        if message["type"] == "http.disconnect":
                            return
                        body.extend(message.get("body", b""))
                        if len(body) > 65536:
                            raise ServiceError("invalid_form", 413)
                        if not message.get("more_body", False):
                            break
                    try:
                        if not supplied:
                            if headers.get(b"content-type", "").startswith("application/json"):
                                data = json.loads(body)
                                supplied = (
                                    data.get("csrf_token", "")
                                    if public_auth and isinstance(data, dict)
                                    else ""
                                )
                            else:
                                supplied = parse_qs(body.decode()).get("csrf_token", [""])[0]
                    except (ValueError, UnicodeError):
                        raise ServiceError("invalid_form", 422) from None
                    delivered = False
                    original = receive

                    async def replay():
                        nonlocal delivered
                        if delivered:
                            return await original()
                        delivered = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}

                    receive = replay
                if account:
                    refreshed = await run_in_threadpool(
                        self.auth.resolve, cookie(self.s.session_cookie), False
                    )
                    if not refreshed:
                        raise ServiceError("authentication_required", 401)
                    principal.set(refreshed)
                    scope["auth_user"] = refreshed
                if (
                    not seed
                    or not isinstance(supplied, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", supplied)
                    or not hmac.compare_digest(supplied, self.auth.csrf(seed))
                ):
                    raise ServiceError("csrf_failed", 403)
                scope["csrf_verified"] = True
            await self.app(scope, receive, secure_send)
        except ServiceError as exc:
            await JSONResponse(
                {"detail": translate(exc.message, language)},
                status_code=exc.status,
                headers={"Retry-After": str(exc.retry_after)} if exc.retry_after else None,
            )(scope, receive, secure_send)
        except (OSError, sqlite3.Error, TimeoutError):
            await JSONResponse({"detail": translate("service_unavailable", language)}, 503)(
                scope, receive, secure_send
            )
        finally:
            principal.reset(token)
