"""Submission and status HTTP contracts."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import ValidationError

from app.api.schemas import JobAccepted, JobStatus, Submission
from app.errors import ServiceError


def router(service):
    api = APIRouter()

    @api.post("/api/jobs", status_code=202, response_model=JobAccepted)
    def submit(
        request: Request,
        submitter_name: Annotated[str, Form(max_length=120)],
        submitter_email: Annotated[str, Form(max_length=254)],
        language: Annotated[str, Form(max_length=2)],
        entities: Annotated[list[str], Form()],
        files: Annotated[list[UploadFile], File()],
    ):
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
        service.registry.select(form.language, form.entities)
        if len(files) > service.settings.max_documents_per_job:
            raise ServiceError("Too many uploaded files.")
        uploaded, size = [], 0
        for file in files:
            data = file.file.read(service.settings.upload_bytes - size + 1)
            size += len(data)
            if size > service.settings.upload_bytes:
                raise ServiceError("Upload exceeds the configured limit.", 413)
            uploaded.append((file.filename or "", data))
        return service.submit(form, uploaded, request.client.host if request.client else "unknown")

    @api.get("/api/jobs/{token}", response_model=JobStatus)
    def status(token: str):
        return service.status(token)

    return api
