"""Public model catalog and component health."""

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse


def router(service):
    api = APIRouter()

    @api.get("/api/languages")
    def languages():
        return [
            {"code": code, "display_name": lang["display_name"]}
            for code, lang in service.registry.languages.items()
        ] + [{"code": "oth", "display_name": "Other"}]

    @api.get("/api/models")
    def models(language: str | None = None):
        return service.registry.public(language)

    @api.get("/health")
    def health():
        return {"status": "ok"}

    @api.get("/ready")
    def ready():
        with service.db.connect() as c:
            heartbeat = c.execute(
                "SELECT value FROM runtime WHERE key='worker_heartbeat'"
            ).fetchone()
        prepared = bool(heartbeat and time.time() - heartbeat[0] < 15)
        return JSONResponse(
            {
                "status": "ready" if prepared else "unavailable",
            },
            status_code=200 if prepared else 503,
        )

    return api
