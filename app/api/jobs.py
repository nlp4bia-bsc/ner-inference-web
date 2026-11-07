"""Submission and status HTTP contracts."""

from fastapi import APIRouter, Request
from pydantic import ValidationError

from app.api.schemas import JobAccepted, JobStatus, ProgressResponse, Submission
from app.auth.origins import trusted_origin
from app.errors import ServiceError


def router(service):
    api = APIRouter()

    @api.delete("/api/jobs/{token}")
    def delete_job(token: str):
        from app.services.document_management import delete_documents

        return delete_documents(service, token)

    @api.delete("/api/my/documents")
    def delete_all():
        from app.services.document_management import delete_all_documents

        return delete_all_documents(service)

    @api.get("/api/my/document-usage")
    def document_usage():
        return service.quota()

    @api.get("/api/my/documents")
    def document_history(
        offset: int = 0, limit: int = 50, state: str | None = None, job_id: str | None = None
    ):
        from app.errors import ServiceError
        from app.permissions.policies import user
        from app.services.document_management import upload_history

        if offset < 0 or not 1 <= limit <= 100:
            raise ServiceError("Invalid pagination.", 422)
        if state and state not in ("STORED", "DELETED", "EXPIRED"):
            raise ServiceError("Invalid document state.", 422)
        return upload_history(service.db, user(), offset, limit, state, job_id)

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
                                "normalize": {"type": "boolean", "default": False},
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
            max_files=service.settings.max_zip_entries,
            max_part_size=int(service.settings.max_document_mb * 1024**2),
        ) as data:
            from app.permissions.policies import user

            account = user()
            if any(key in data for key in ("owner_user_id", "system_role", "access_tier")):
                raise ServiceError("invalid_form", 422)
            try:
                form = Submission(
                    submitter_name=data.get("submitter_name", account["full_name"]),
                    submitter_email=data.get("submitter_email", account["email"]),
                    language=data.get("language", ""),
                    normalize=data.get("normalize", "false"),
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
            accepted = await run_in_threadpool(
                service.submit_streams,
                form,
                streams,
                request.client.host if request.client else "unknown",
                mode,
                request.scope.get("admission_lease"),
            )
            browser_origin = str(request.base_url).rstrip("/")
            if trusted_origin(browser_origin, service.settings):
                accepted["url"] = (
                    browser_origin + service.settings.app_prefix + "/jobs/" + accepted["job_id"]
                )
            return accepted

    @api.get("/api/jobs/{token}", response_model=JobStatus)
    def status(token: str):
        return service.status(token)

    @api.get("/api/jobs/{token}/progress", response_model=ProgressResponse)
    def progress(token: str):
        from app.services.jobs import iso

        data = service.status(token)
        result = data["progress"]
        result["updated_at"] = iso(result["updated_at"])
        result.update(
            server_now=data["server_now"],
            expires_at=data["expires_at"],
            queue_position=data["queue_position"],
        )
        return result

    return api
