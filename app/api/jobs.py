"""Submission and status HTTP contracts."""

from fastapi import APIRouter, Request
from pydantic import ValidationError

from app.api.schemas import JobAccepted, JobStatus, ProgressResponse, Submission
from app.errors import ServiceError


def router(service):
    api = APIRouter()

    @api.post(
        "/api/jobs",
        status_code=202,
        response_model=JobAccepted,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "submitter_name": {"type": "string"},
                                "submitter_email": {"type": "string", "format": "email"},
                                "language": {"type": "string"},
                                "entities": {"type": "array", "items": {"type": "string"}},
                                "models": {"type": "array", "items": {"type": "string"}},
                                "input_mode": {
                                    "type": "string",
                                    "enum": ["PASTED_TEXT", "TXT_UPLOAD", "ZIP_ENTRY"],
                                },
                                "pasted_text": {"type": "string"},
                                "pasted_text_file": {"type": "string", "format": "binary"},
                                "document_name": {"type": "string"},
                                "files": {
                                    "type": "array",
                                    "items": {"type": "string", "format": "binary"},
                                },
                            },
                            "required": [
                                "submitter_name",
                                "submitter_email",
                                "language",
                            ],
                        }
                    }
                },
            }
        },
    )
    async def submit(request: Request):
        import io

        from starlette.concurrency import run_in_threadpool
        from starlette.datastructures import UploadFile

        async with request.form(
            max_files=service.settings.max_documents_per_job,
            max_part_size=int(service.settings.max_document_mb * 1024**2),
        ) as data:
            try:
                form = Submission(
                    submitter_name=data.get("submitter_name", ""),
                    submitter_email=data.get("submitter_email", ""),
                    language=data.get("language", ""),
                    entities=data.getlist("entities"),
                    models=data.getlist("models") if "models" in data else None,
                )
            except ValidationError:
                raise ServiceError(
                    "Enter your name, a valid email, language and entity types."
                ) from None
            files = [f for f in data.getlist("files") if isinstance(f, UploadFile) and f.filename]
            text = data.get("pasted_text")
            pasted_file = data.get("pasted_text_file")
            if (text is not None or pasted_file is not None) and files:
                raise ServiceError("Choose exactly one input mode.")
            mode = data.get("input_mode") or (
                "PASTED_TEXT"
                if (text is not None or pasted_file is not None)
                else "ZIP_ENTRY"
                if len(files) == 1 and files[0].filename.lower().endswith(".zip")
                else "TXT_UPLOAD"
            )
            if mode == "PASTED_TEXT":
                if (
                    files
                    or (text is not None and pasted_file is not None)
                    or (not isinstance(text, str) and not isinstance(pasted_file, UploadFile))
                ):
                    raise ServiceError("Paste text without files.")
                streams = [
                    (
                        data.get("document_name") or "pasted-text.txt",
                        pasted_file.file
                        if isinstance(pasted_file, UploadFile)
                        else io.BytesIO(text.encode("utf-8")),
                    )
                ]
            elif mode in ("TXT_UPLOAD", "ZIP_ENTRY"):
                if (
                    (text is not None or pasted_file is not None)
                    or not files
                    or (
                        mode == "ZIP_ENTRY"
                        and (len(files) != 1 or not files[0].filename.lower().endswith(".zip"))
                    )
                    or (
                        mode == "TXT_UPLOAD" and any(not f.filename.endswith(".txt") for f in files)
                    )
                ):
                    raise ServiceError("Select TXT files or one ZIP, without pasted text.")
                streams = [(f.filename, f.file) for f in files]
            else:
                raise ServiceError("Unknown input mode.")
            return await run_in_threadpool(
                service.submit_streams,
                form,
                streams,
                request.client.host if request.client else "unknown",
                mode,
                request.scope.get("admission_lease"),
            )

    @api.get("/api/jobs/{token}", response_model=JobStatus)
    def status(token: str):
        return service.status(token)

    @api.get("/api/jobs/{token}/progress", response_model=ProgressResponse)
    def progress(token: str):
        import time

        from app.persistence.progress import ProgressRepository
        from app.services.jobs import iso

        job = service.available(token)
        result = ProgressRepository(service.db).snapshot(job)
        result["updated_at"] = iso(result["updated_at"])
        result.update(
            server_now=iso(time.time()),
            expires_at=iso(job["expires_at"]),
            queue_position=service.status(token)["queue_position"],
        )
        return result

    return api
