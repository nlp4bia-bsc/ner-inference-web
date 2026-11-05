"""Server-rendered application pages, with one shared base path."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse


def router(service, templates):
    api = APIRouter()

    @api.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "max_documents": service.settings.max_documents_per_job,
                "max_upload_mb": service.settings.max_upload_mb,
                "ttl": service.settings.job_results_ttl_hours,
                "prefix": service.settings.app_prefix,
            },
        )

    @api.get("/jobs/{token}", response_class=HTMLResponse, include_in_schema=False)
    def job(request: Request, token: str):
        service.db.get(token)
        return templates.TemplateResponse(
            request=request, name="job.html", context={"prefix": service.settings.app_prefix}
        )

    @api.get("/api/jobs/{token}/viewer", response_class=HTMLResponse, include_in_schema=False)
    def viewer(request: Request, token: str):
        service.completed(token)
        return templates.TemplateResponse(
            request=request, name="viewer.html", context={"prefix": service.settings.app_prefix}
        )

    return api
