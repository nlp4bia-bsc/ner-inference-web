"""Server-rendered application pages, with one shared base path."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


def router(service, templates):
    api = APIRouter()

    @api.get("/documents", response_class=HTMLResponse, include_in_schema=False)
    def my_documents(request: Request):
        from app.permissions.policies import user

        account, owner = user(), None
        identity = request.query_params.get("job")
        administrative_scope = False
        if identity and account["system_role"] == "ADMIN":
            job = service.available(identity)
            administrative_scope = job["owner_user_id"] != account["id"]
            if administrative_scope:
                with service.db.connect() as connection:
                    row = connection.execute(
                        "SELECT full_name,email FROM users WHERE id=?", (job["owner_user_id"],)
                    ).fetchone()
                    owner = dict(row) if row else None
        return templates.TemplateResponse(
            request=request,
            name="documents.html",
            context={
                "prefix": service.settings.app_prefix,
                "administrative_scope": administrative_scope,
                "document_owner": owner,
            },
        )

    @api.get("/annotate", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request):
        from app.errors import ServiceError
        from app.permissions.policies import document_limit, user

        account = user()
        if service.settings.require_email_verification and not account["email_verified_at"]:
            raise ServiceError("verification_required", 403)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "max_documents": document_limit(
                    account["access_tier"],
                    service.settings.max_documents_per_job,
                    override=account["document_limit"],
                ),
                "account": account,
                "csrf": request.app.state.auth.csrf(account["csrf_seed"]),
                "max_upload_mb": service.settings.max_upload_mb,
                "ttl": service.settings.job_results_ttl_hours,
                "prefix": service.settings.app_prefix,
            },
        )

    @api.get("/jobs/{token}", response_class=HTMLResponse, include_in_schema=False)
    def job(request: Request, token: str):
        service.available(token)
        return templates.TemplateResponse(
            request=request, name="job.html", context={"prefix": service.settings.app_prefix}
        )

    @api.get("/jobs/{token}/viewer", response_class=HTMLResponse, include_in_schema=False)
    @api.get("/api/jobs/{token}/viewer", response_class=HTMLResponse, include_in_schema=False)
    def viewer(request: Request, token: str):
        service.available(token)
        return templates.TemplateResponse(
            request=request, name="viewer.html", context={"prefix": service.settings.app_prefix}
        )

    @api.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    def api_reference(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="api.html",
            context={"prefix": service.settings.app_prefix, "schema": request.app.openapi()},
        )

    @api.get("/models", response_class=HTMLResponse, include_in_schema=False)
    def models(request: Request):
        return templates.TemplateResponse(
            request=request, name="models.html", context={"prefix": service.settings.app_prefix}
        )

    return api
