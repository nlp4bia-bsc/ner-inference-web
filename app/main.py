"""FastAPI composition root. Domain operations live in services, HTTP contracts in api."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app.admin import routes as admin_routes
from app.api import catalog, documents, downloads, jobs, pages
from app.api.errors import register_errors
from app.api.middleware import AdmissionMiddleware
from app.auth import routes as auth_routes
from app.auth.email import Mailer
from app.auth.middleware import AuthMiddleware
from app.auth.service import AuthService
from app.config import Settings
from app.db import Database
from app.services.cleanup import cleanup
from app.services.jobs import JobService
from app.services.registry import Registry
from app.storage import LocalStorage
from app.ui import context as ui_context


def create_app(settings: Settings | None = None) -> FastAPI:
    os.umask(0o077)
    settings = settings or Settings()
    storage, db, registry = (
        LocalStorage(settings.storage_root),
        Database(settings),
        Registry(settings),
    )
    mailer = Mailer(settings, db)
    auth = AuthService(settings, db, mailer)
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

        async def deliver():
            while True:
                try:
                    await run_in_threadpool(mailer.flush)
                except Exception:
                    import logging

                    logging.getLogger("temu.email").error("email_dispatch_unavailable")
                await asyncio.sleep(1)

        mail_task = asyncio.create_task(deliver())
        task = asyncio.create_task(sweep())
        yield
        mail_task.cancel()
        task.cancel()
        await asyncio.gather(task, mail_task, return_exceptions=True)

    app = FastAPI(
        title="NLP4BIA · Multilingual NER Platform",
        version="0.6.2",
        lifespan=lifespan,
        redirect_slashes=False,
        docs_url=None,
        openapi_url=settings.app_prefix + "/openapi.json",
        redoc_url=None,
    )
    app.state.db, app.state.registry, app.state.settings = db, registry, settings
    app.state.jobs = service
    app.state.auth, app.state.mailer = auth, mailer
    app.add_middleware(AdmissionMiddleware, settings=settings, db=db)
    app.add_middleware(AuthMiddleware, auth=auth)
    base = Path(__file__).parent
    app.mount(
        settings.app_prefix + "/static", StaticFiles(directory=base / "static"), name="static"
    )
    templates = Jinja2Templates(directory=base / "templates", context_processors=[ui_context])
    register_errors(app)
    app.include_router(auth_routes.router(auth, templates, service), prefix=settings.app_prefix)
    app.include_router(
        admin_routes.router(db, settings, auth, templates), prefix=settings.app_prefix
    )
    for module in (catalog, jobs, downloads, documents):
        app.include_router(module.router(service), prefix=settings.app_prefix)
    app.include_router(pages.router(service, templates), prefix=settings.app_prefix)
    return app
