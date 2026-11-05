"""FastAPI composition root. Domain operations live in services, HTTP contracts in api."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app.api import catalog, documents, downloads, jobs, pages
from app.api.errors import register_errors
from app.api.middleware import AdmissionMiddleware
from app.config import Settings
from app.db import Database
from app.services.cleanup import cleanup
from app.services.jobs import JobService
from app.services.registry import Registry
from app.storage import LocalStorage


def create_app(settings: Settings | None = None) -> FastAPI:
    os.umask(0o077)
    settings = settings or Settings()
    storage, db, registry = (
        LocalStorage(settings.storage_root),
        Database(settings),
        Registry(settings),
    )
    service = JobService(settings, db, storage, registry)

    @asynccontextmanager
    async def lifespan(app):
        async def sweep():
            while True:
                try:
                    await run_in_threadpool(cleanup, db, storage)
                except Exception:
                    import logging

                    logging.getLogger("temu.cleanup").error("cleanup_failed")
                await asyncio.sleep(settings.cleanup_interval_seconds)

        task = asyncio.create_task(sweep())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app = FastAPI(
        title="TEMU Multilingual NER",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        openapi_url=settings.app_prefix + "/openapi.json",
        redoc_url=None,
    )
    app.state.db, app.state.registry, app.state.settings = db, registry, settings
    app.state.jobs = service
    app.add_middleware(AdmissionMiddleware, settings=settings, db=db)
    base = Path(__file__).parent
    app.mount(
        settings.app_prefix + "/static", StaticFiles(directory=base / "static"), name="static"
    )
    templates = Jinja2Templates(directory=base / "templates")
    register_errors(app)
    for module in (catalog, jobs, downloads, documents):
        app.include_router(module.router(service), prefix=settings.app_prefix)
    app.include_router(pages.router(service, templates), prefix=settings.app_prefix)
    return app
