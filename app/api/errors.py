"""Safe HTTP errors without echoing clinical inputs."""

import sqlite3

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import ServiceError
from app.ui_i18n import translate


def register_errors(app):
    @app.exception_handler(OSError)
    @app.exception_handler(sqlite3.Error)
    async def infrastructure_error(request, exc):
        import logging

        logging.getLogger("temu.api").error(
            "infrastructure_failed error_type=%s", type(exc).__name__
        )
        return JSONResponse(
            {"detail": translate("service_unavailable", request.scope.get("auth_locale", "en"))},
            status_code=503,
        )

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse(
            {"detail": translate(exc.message, request.scope.get("auth_locale", "en"))},
            status_code=exc.status,
            headers={"Retry-After": str(exc.retry_after)} if exc.retry_after else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI default error bodies echo user inputs; return only safe field locations.
        return JSONResponse(
            {
                "detail": translate(
                    "Check your name, email, language, entities and files.",
                    request.scope.get("auth_locale", "en"),
                ),
                "fields": [str(e["loc"][-1]) for e in exc.errors()],
            },
            status_code=422,
        )
