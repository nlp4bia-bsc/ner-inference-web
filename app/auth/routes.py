"""Localized HTML flows and JSON APIs share the same validated account operations."""

import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from app.auth.i18n import locale, translate
from app.auth.service import public_user
from app.domain.identity import EmailAddress
from app.errors import ServiceError
from app.permissions.policies import user
from app.ui_i18n import translate as ui_translate
from app.users.schemas import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    Login,
    PasswordChange,
    Profile,
    Register,
    SafeModel,
)


class EmailInput(SafeModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailAddress


class TokenInput(SafeModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$")


class ResetInput(TokenInput):
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    password_confirmation: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )


class MfaStart(SafeModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(max_length=1024)


class MfaConfirm(SafeModel):
    model_config = ConfigDict(extra="forbid")
    otp: str = Field(max_length=100, pattern=r"^[A-Za-z0-9-]*$")


async def data(request):
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            value = await request.json()
            if not isinstance(value, dict):
                raise ValueError()
        else:
            value = dict(await request.form(max_files=0, max_fields=30, max_part_size=65536))
        value.pop("csrf_token", None)
        return value
    except (ValueError, TypeError, HTTPException):
        raise ServiceError("invalid_form", 422) from None


def validate(schema, value):
    try:
        return schema.model_validate(value)
    except ValidationError:
        raise ServiceError("invalid_form", 422) from None


def router(auth, templates, jobs):
    api = APIRouter()
    prefix = auth.s.app_prefix

    def render(request, mode, message=None, status=200, **extra):
        account = request.scope.get("auth_user")
        if mode in ("login", "register", "verify", "forgot", "reset", "resend") or extra.get(
            "recovery_codes"
        ):
            # Recovery codes are shown once after revoking the enrollment session.
            # Do not attach a session guard that immediately hides that result.
            account = None
        language = locale(request.scope.get("auth_locale"))
        challenge = request.cookies.get("temu_challenge") or secrets.token_urlsafe(32)
        seed = (
            account["csrf_seed"]
            if account and mode not in ("login", "register", "verify", "forgot", "reset", "resend")
            else challenge
        )
        response = templates.TemplateResponse(
            request=request,
            name="auth.html",
            context={
                "mode": mode,
                "t": lambda key: translate(key, language),
                "locale": language,
                "prefix": prefix,
                "csrf": auth.csrf(seed),
                "account": public_user(account, auth.s) if account else None,
                "message": ui_translate(message, language) if message else None,
                "message_key": message,
                "token": request.query_params.get("token", ""),
                "password_min_length": PASSWORD_MIN_LENGTH,
                "password_max_length": PASSWORD_MAX_LENGTH,
                **extra,
            },
            status_code=status,
        )
        response.set_cookie(
            "temu_challenge",
            challenge,
            httponly=True,
            secure=auth.s.cookie_secure,
            samesite="lax",
            path=auth.s.cookie_path,
            max_age=3600,
        )
        response.set_cookie(
            "temu_locale",
            language,
            httponly=True,
            secure=auth.s.cookie_secure,
            samesite="lax",
            path=auth.s.cookie_path,
            max_age=365 * 86400,
        )
        return response

    def redirect(path, language):
        return RedirectResponse(
            prefix + path + ("&" if "?" in path else "?") + "lang=" + locale(language), 303
        )

    def set_session(response, raw):
        account = auth.resolve(raw)
        remaining = max(
            1, int(account["session_expires_at"] - datetime.now(timezone.utc).timestamp())
        )
        response.set_cookie(
            auth.s.session_cookie,
            raw,
            httponly=True,
            secure=auth.s.cookie_secure,
            samesite="lax",
            path=auth.s.cookie_path,
            max_age=remaining,
        )
        return response

    def clear_session(response):
        response.delete_cookie(
            auth.s.session_cookie,
            path=auth.s.cookie_path,
            httponly=True,
            secure=auth.s.cookie_secure,
            samesite="lax",
        )
        return response

    @api.get("/api/auth/session")
    def session():
        account = user()
        return {"user": public_user(account, auth.s), "csrf_token": auth.csrf(account["csrf_seed"])}

    schemas = {
        "login": Login,
        "register": Register,
        "verify-email": TokenInput,
        "resend-verification": EmailInput,
        "forgot-password": EmailInput,
        "reset-password": ResetInput,
        "change-password": PasswordChange,
        "profile": Profile,
        "mfa/start": MfaStart,
        "mfa/confirm": MfaConfirm,
    }
    modes = {
        "login": "login",
        "register": "register",
        "verify-email": "verify",
        "resend-verification": "resend",
        "forgot-password": "forgot",
        "reset-password": "reset",
        "change-password": "password",
        "profile": "profile",
        "mfa/start": "mfa",
        "mfa/confirm": "mfa",
    }

    async def operation(request, operation, is_api):
        language = locale(request.scope.get("auth_locale"))
        ip = request.client.host if request.client else "unknown"
        try:
            values = await data(request)
            form = validate(schemas[operation], values) if operation in schemas else None
            response_token = None
            message = "saved"
            target = "/profile"
            extra = {}
            if operation == "register":
                await run_in_threadpool(auth.register, form, ip)
                if auth.s.require_email_verification:
                    message = "email_sent"
                else:
                    message, target = "account_created", "/login"
            elif operation == "login":
                response_token = await run_in_threadpool(auth.login, form, ip)
                # Revoke an existing pre-login session to prevent session fixation.
                previous = request.scope.get("auth_user")
                if previous:
                    await run_in_threadpool(auth.logout, previous)
                target = "/"
            elif operation == "verify-email":
                await run_in_threadpool(auth.throttle, "consume-verify", form.token, ip)
                await run_in_threadpool(auth.consume, "verify", form.token)
                message, target = "verified", "/login"
            elif operation in ("resend-verification", "forgot-password"):
                await run_in_threadpool(
                    auth.email_action,
                    "verify" if operation == "resend-verification" else "reset",
                    str(form.email),
                    ip,
                )
                message = "email_sent"
            elif operation == "reset-password":
                await run_in_threadpool(auth.throttle, "consume-reset", form.token, ip)
                if form.password != form.password_confirmation:
                    raise ServiceError("invalid_form", 422)
                await run_in_threadpool(auth.consume, "reset", form.token, form.password)
                message, target = "password_changed", "/login"
            elif operation == "change-password":
                await run_in_threadpool(auth.change_password, user(), form, ip)
                message, target = "password_changed", "/login"
            elif operation == "touch":
                if values:
                    raise ServiceError("invalid_form", 422)
                user()
            elif operation in ("logout", "logout-all"):
                if values:
                    raise ServiceError("invalid_form", 422)
                await run_in_threadpool(auth.logout, user(), operation == "logout-all")
                target = "/login"
            elif operation == "rotate-session":
                if values:
                    raise ServiceError("invalid_form", 422)
                response_token = await run_in_threadpool(auth.rotate, user())
            elif operation == "profile":
                await run_in_threadpool(auth.profile, user(), form)
                language = form.preferred_locale
            elif operation == "mfa/start":
                extra["secret"] = await run_in_threadpool(
                    auth.start_mfa, user(), form.current_password, ip
                )
            elif operation == "mfa/confirm":
                extra["recovery_codes"] = await run_in_threadpool(
                    auth.confirm_mfa, user(), form.otp, ip
                )
                target = "/login"
            if is_api:
                response = JSONResponse(
                    {"message": translate(message, language), "redirect": prefix + target, **extra}
                )
            elif operation == "login" or operation in (
                "logout",
                "logout-all",
                "rotate-session",
                "profile",
            ):
                response = redirect(target, language)
            else:
                mode = (
                    "mfa"
                    if operation == "mfa/confirm"
                    else "login"
                    if target == "/login"
                    else modes.get(operation, "profile")
                )
                response = render(request, mode, message, **extra)
            if operation == "profile":
                response.set_cookie(
                    "temu_locale",
                    language,
                    httponly=True,
                    secure=auth.s.cookie_secure,
                    samesite="lax",
                    path=auth.s.cookie_path,
                    max_age=365 * 86400,
                )
            if response_token:
                response = await run_in_threadpool(set_session, response, response_token)
            if operation in (
                "logout",
                "logout-all",
                "reset-password",
                "change-password",
                "mfa/confirm",
            ):
                clear_session(response)
            return response
        except ServiceError as exc:
            if is_api:
                raise
            return render(request, modes.get(operation, "profile"), exc.message, exc.status)

    for name in [*schemas, "logout", "logout-all", "rotate-session", "touch"]:

        def endpoint(operation_name, api_response):
            async def call(request: Request):
                return await operation(request, operation_name, api_response)

            return call

        api.add_api_route(
            "/api/auth/" + name,
            endpoint(name, True),
            methods=["PATCH" if name == "profile" else "POST"],
            name="auth_" + name,
        )
        api.add_api_route(
            "/" + name, endpoint(name, False), methods=["POST"], include_in_schema=False
        )

    for path, mode in [
        ("/login", "login"),
        ("/register", "register"),
        ("/verify-email", "verify"),
        ("/resend-verification", "resend"),
        ("/forgot-password", "forgot"),
        ("/reset-password", "reset"),
        ("/profile", "profile"),
        ("/change-password", "password"),
        ("/mfa", "mfa"),
    ]:

        def page(page_mode):
            def get(request: Request):
                return render(request, page_mode)

            return get

        api.add_api_route(path, page(mode), methods=["GET"], include_in_schema=False)

    @api.get("/", include_in_schema=False)
    @api.get("/dashboard", include_in_schema=False)
    @api.get("/my-jobs", include_in_schema=False)
    def dashboard(request: Request, offset: int = 0):
        if offset < 0:
            raise ServiceError("invalid_form", 422)
        account = user()
        language = locale(request.scope.get("auth_locale"))
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "prefix": prefix,
                "account": public_user(account, auth.s),
                "csrf": auth.csrf(account["csrf_seed"]),
                "locale": language,
                "t": lambda key: translate(key, language),
                "jobs": jobs.history(offset),
                "workspace_metrics": jobs.workspace_metrics(),
                "offset": offset,
                "date": lambda value: (
                    datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="minutes")
                    if value
                    else "—"
                ),
            },
        )

    def active_sessions():
        account = user()
        now = time.time()
        with auth.db.connect() as c:
            rows = c.execute(
                """SELECT created_at,last_seen_at,expires_at,token_hash=? AS current
                FROM sessions WHERE user_id=? AND auth_version=? AND revoked_at IS NULL
                AND expires_at>? AND last_seen_at>? ORDER BY created_at DESC LIMIT 100""",
                (
                    account["session_hash"],
                    account["id"],
                    account["auth_version"],
                    now,
                    now - auth.s.session_idle_seconds,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    @api.get("/api/auth/sessions")
    def sessions_api():
        return active_sessions()

    @api.get("/sessions", include_in_schema=False)
    def sessions_page(request: Request):
        return render(
            request,
            "sessions",
            sessions=active_sessions(),
            date=lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat(),
        )

    @api.get("/account-deletion", include_in_schema=False)
    def deletion_page(request: Request):
        return render(request, "deletion")

    @api.post("/account-deletion", include_in_schema=False)
    async def deletion_request(request: Request):
        from app.auth.service import audit
        from app.auth.sessions import require_live

        if await data(request):
            raise ServiceError("invalid_form", 422)
        account = user()
        auth.throttle(
            "deletion-request",
            account["email"],
            request.client.host if request.client else "unknown",
        )
        with auth.db.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            require_live(c, account, auth.s)
            audit(c, account["id"], account["id"], "ACCOUNT_DELETION_REQUESTED")
        return render(
            request, "deletion", "Your deletion request has been recorded for institutional review."
        )

    @api.patch("/api/profile")
    async def patch_profile(request: Request):
        return await operation(request, "profile", True)

    @api.get("/api/profile")
    def profile():
        return public_user(user(), auth.s)

    @api.get("/api/my/jobs")
    def history(offset: int = 0):
        if offset < 0:
            raise ServiceError("invalid_form", 422)
        return jobs.history(offset)

    return api
