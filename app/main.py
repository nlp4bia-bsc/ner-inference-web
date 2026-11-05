import asyncio
import json
import os
import secrets
import shutil
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.db import Database
from app.errors import ServiceError
from app.services.cleanup import cleanup
from app.services.documents import load_documents
from app.services.registry import Registry
from app.storage import LocalStorage

BASE = Path(__file__).parent


class Submission(BaseModel):
    submitter_name: str = Field(min_length=1, max_length=120)
    submitter_email: EmailStr
    language: str = Field(pattern="^[a-z]{2}$")
    entities: list[str] = Field(min_length=1, max_length=100)

    @field_validator("submitter_name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Enter your name")
        return value.strip()

    @field_validator("submitter_email", mode="after")
    @classmethod
    def normalize_email(cls, value):
        return str(value).lower()


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


class AdmissionMiddleware:
    """Bound actual bytes even with chunked encoding, before multipart parsing."""

    def __init__(self, app, settings, db):
        self.app, self.s, self.db = app, settings, db

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope["headers"]}

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
                ]
            await send(message)

        if scope["method"] != "POST" or scope["path"] != "/api/jobs":
            return await self.app(scope, receive, secure_send)
        lease = None
        try:
            origin = headers.get(b"origin")
            if origin and origin.decode().rstrip("/") != self.s.public_base_url.rstrip("/"):
                raise ServiceError("Untrusted request origin.", 403)
            maximum = self.s.upload_bytes + 1024**2  # bounded multipart overhead
            try:
                length = int(headers.get(b"content-length", b"0"))
            except ValueError:
                raise ServiceError("Invalid Content-Length.", 400) from None
            if length > maximum:
                raise ServiceError("Upload exceeds the configured limit.", 413)
            lease = await run_in_threadpool(self.db.reserve_upload)
            chunks, size = [], 0
            async with asyncio.timeout(300):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    size += len(message.get("body", b""))
                    if size > maximum:
                        raise ServiceError("Upload exceeds the configured limit.", 413)
                    chunks.append(message.get("body", b""))
                    if not message.get("more_body", False):
                        break
            body, delivered = b"".join(chunks), False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            await self.app(scope, replay, secure_send)
        except (ServiceError, TimeoutError) as exc:
            status = exc.status if isinstance(exc, ServiceError) else 408
            message = exc.message if isinstance(exc, ServiceError) else "Upload timed out."
            await JSONResponse({"detail": message}, status_code=status)(scope, receive, secure_send)
        finally:
            if lease:
                await run_in_threadpool(self.db.release_upload, lease)


def create_app(settings: Settings | None = None) -> FastAPI:
    os.umask(0o077)
    s = settings or Settings()
    storage, db, registry = LocalStorage(s.storage_root), Database(s), Registry(s)

    @asynccontextmanager
    async def lifespan(app):
        async def sweeper():
            while True:
                try:
                    await run_in_threadpool(cleanup, db, storage)
                except Exception:
                    import logging

                    logging.getLogger("temu.cleanup").error("cleanup_failed")
                await asyncio.sleep(s.cleanup_interval_seconds)

        task = asyncio.create_task(sweeper())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app = FastAPI(title="TEMU Multilingual NER", version="0.1.0", lifespan=lifespan)
    app.state.db, app.state.registry, app.state.settings = db, registry, s
    app.add_middleware(AdmissionMiddleware, settings=s, db=db)
    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
    templates = Jinja2Templates(directory=BASE / "templates")

    @app.exception_handler(OSError)
    @app.exception_handler(sqlite3.Error)
    async def infrastructure_error(request, exc):
        import logging

        logging.getLogger("temu.api").error(
            "infrastructure_failed error_type=%s", type(exc).__name__
        )
        return JSONResponse(
            {"detail": "The service is temporarily unavailable. Please try again later."},
            status_code=503,
        )

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse(
            {"detail": exc.message},
            status_code=exc.status,
            headers={"Retry-After": str(exc.retry_after)} if exc.retry_after else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI default error bodies echo user inputs; return only safe field locations.
        return JSONResponse(
            {
                "detail": "Check your name, email, language, entities and files.",
                "fields": [str(e["loc"][-1]) for e in exc.errors()],
            },
            status_code=422,
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "max_documents": s.max_documents_per_job,
                "max_upload_mb": s.max_upload_mb,
                "ttl": s.job_results_ttl_hours,
            },
        )

    @app.get("/jobs/{token}", response_class=HTMLResponse, include_in_schema=False)
    def job_page(request: Request, token: str):
        db.get(token)
        return templates.TemplateResponse(request=request, name="job.html")

    @app.get("/api/languages")
    def languages():
        return [
            {"code": code, "display_name": lang["display_name"]}
            for code, lang in registry.languages.items()
        ]

    @app.get("/api/models")
    def models(language: str | None = None):
        return registry.public(language)

    @app.post("/api/jobs", status_code=202)
    def submit(
        request: Request,
        submitter_name: Annotated[str, Form(max_length=120)],
        submitter_email: Annotated[str, Form(max_length=254)],
        language: Annotated[str, Form(max_length=2)],
        entities: Annotated[list[str], Form()],
        files: Annotated[list[UploadFile], File()],
    ):
        from pydantic import ValidationError

        try:
            form = Submission(
                submitter_name=submitter_name,
                submitter_email=submitter_email,
                language=language,
                entities=entities,
            )
        except ValidationError:
            raise ServiceError(
                "Enter your name, a valid email, language and entity types."
            ) from None
        selected = registry.select(form.language, form.entities)
        if len(files) > s.max_documents_per_job:
            raise ServiceError("Too many uploaded files.")
        uploaded, size = [], 0
        for file in files:
            data = file.file.read(s.upload_bytes - size + 1)
            size += len(data)
            if size > s.upload_bytes:
                raise ServiceError("Upload exceeds the configured limit.", 413)
            uploaded.append((file.filename or "", data))
        documents = load_documents(uploaded, s)
        job_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        staging = storage.root / "staging" / job_id
        staging.mkdir()
        try:
            for name, data in documents.items():
                path = staging / "input" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            payload = {
                **form.model_dump(),
                "documents": list(documents),
                "selected_models": [
                    {
                        k: m.get(k)
                        for k in (
                            "model_id",
                            "version",
                            "model_dir",
                            "checkpoint_sha256",
                            "min_score",
                            "batch_size",
                        )
                    }
                    for m in selected
                ],
            }
            # Rename before database commit: worker can never claim a job without input.
            staging.rename(storage.job(job_id))
            ip = request.client.host if request.client else "unknown"
            db.accept(job_id, token, payload, len(documents), ip)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            storage.delete(job_id)
            raise
        url = s.public_base_url.rstrip("/") + "/jobs/" + token
        return {"job_id": job_id, "status": "QUEUED", "token": token, "url": url}

    def available_job(token):
        job = db.get(token)
        if job["status"] == "EXPIRED" or (job["expires_at"] and job["expires_at"] <= time.time()):
            raise ServiceError("Results have expired and downloads are no longer available.", 410)
        return job

    @app.get("/api/jobs/{token}")
    def status(token: str):
        job = available_job(token)
        payload = json.loads(job["payload"])
        with db.connect() as c:
            position = (
                c.execute(
                    "SELECT count(*) FROM jobs WHERE status='QUEUED' AND seq<=?", (job["seq"],)
                ).fetchone()[0]
                if job["status"] == "QUEUED"
                else None
            )
        return {
            "job_id": job["id"],
            "status": job["status"],
            "document_count": job["document_count"],
            "processed_documents": job["processed_documents"],
            "queue_position": position,
            "language": payload["language"],
            "entities": payload["entities"],
            "created_at": iso(job["created_at"]),
            "started_at": iso(job["started_at"]),
            "completed_at": iso(job["completed_at"]),
            "expires_at": iso(job["expires_at"]),
            "error_summary": job["error_summary"],
            "summary": json.loads(job["summary"]) if job["summary"] else None,
            "downloads_available": job["status"] == "COMPLETED",
        }

    def result_path(token, name):
        job = available_job(token)
        if job["status"] != "COMPLETED":
            raise ServiceError("Results are not ready.", 409)
        path = storage.job(job["id"]) / "output" / name
        if not path.is_file():
            raise ServiceError("Result temporarily unavailable.", 503)
        return path

    @app.get("/api/jobs/{token}/download/brat", response_class=FileResponse)
    def brat(token: str):
        return FileResponse(
            result_path(token, "results.zip"),
            filename="ner_results.zip",
            media_type="application/zip",
        )

    @app.get("/api/jobs/{token}/download/tsv", response_class=FileResponse)
    def tsv(token: str):
        return FileResponse(
            result_path(token, "annotations.tsv"),
            filename="annotations.tsv",
            media_type="text/tab-separated-values",
        )

    @app.get("/api/jobs/{token}/statistics")
    def stats(token: str):
        return json.loads(result_path(token, "statistics.json").read_text())

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        with db.connect() as c:
            heartbeat = c.execute(
                "SELECT value FROM runtime WHERE key='worker_heartbeat'"
            ).fetchone()
        prepared = bool(heartbeat and time.time() - heartbeat[0] < 15)
        return JSONResponse(
            {
                "status": "ready" if prepared else "unavailable",
                "models_available": any(e["available"] for e in registry.public()),
            },
            status_code=200 if prepared else 503,
        )

    return app
