from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.admin.explorer import AdminExplorer
from app.admin.service import AdminService
from app.auth.i18n import locale, translate
from app.auth.routes import data, validate
from app.errors import ServiceError
from app.permissions.policies import require_admin
from app.users.schemas import AccessReview, AdminChange, DeleteAccount


def router(db, settings, auth, templates, jobs):
    api = APIRouter(dependencies=[Depends(require_admin)])
    service = AdminService(db, settings, jobs, auth)
    explorer = AdminExplorer(jobs)
    prefix = settings.app_prefix

    @api.get("/api/admin/explorer/statistics")
    def explorer_statistics():
        return explorer.overview()

    @api.get("/api/admin/explorer/users")
    def explorer_users(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
        return explorer.users(offset, limit)

    @api.get("/api/admin/explorer/users/{identity}/projects")
    def explorer_projects(
        identity: str, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)
    ):
        return explorer.projects(identity, offset, limit)

    @api.get("/api/admin/explorer/projects/{identity}")
    def explorer_documents(
        identity: str, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)
    ):
        return explorer.project(identity, offset, limit)

    @api.get("/api/admin/users")
    def users(
        q: str = Query("", max_length=200),
        offset: int = Query(0, ge=0),
        approval: Literal["PENDING", "APPROVED", "REJECTED", "DELETING"] | None = None,
    ):
        return service.users(q, offset, approval)

    @api.patch("/api/admin/users/{identity}")
    async def change(identity: str, request: Request):
        form = validate(AdminChange, await data(request))
        await run_in_threadpool(service.change, identity, form)
        return {"message": translate("saved", request.scope["auth_locale"])}

    @api.post("/api/admin/users/{identity}/review")
    async def review(identity: str, request: Request):
        form = validate(AccessReview, await data(request))
        await run_in_threadpool(service.review, identity, form.decision)
        return {"message": translate("saved", request.scope["auth_locale"])}

    @api.delete("/api/admin/users/{identity}")
    async def delete_account(identity: str, request: Request):
        form = validate(DeleteAccount, await data(request))
        return await run_in_threadpool(service.delete_account, identity, form.confirm_email)

    @api.get("/api/admin/projects")
    def projects(q: str = Query("", max_length=200), offset: int = Query(0, ge=0)):
        return service.projects(q, offset)

    @api.delete("/api/admin/projects/{identity}")
    async def delete_project(identity: str, request: Request):
        if await data(request):
            raise ServiceError("invalid_form", 422)
        return await run_in_threadpool(service.delete_project, identity)

    @api.post("/api/admin/users/{identity}/revoke-sessions")
    async def revoke(identity: str, request: Request):
        if await data(request):
            raise ServiceError("invalid_form", 422)
        await run_in_threadpool(service.revoke, identity)
        return {"message": translate("saved", request.scope["auth_locale"])}

    @api.get("/api/admin/metrics")
    def metrics():
        return service.metrics()

    @api.get("/api/admin/audit")
    def history(offset: int = Query(0, ge=0)):
        return service.history(offset)

    @api.get("/admin", include_in_schema=False)
    def page(request: Request, q: str = Query("", max_length=200), offset: int = Query(0, ge=0)):
        actor = require_admin()
        language = locale(request.scope["auth_locale"])
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={
                "prefix": prefix,
                "locale": language,
                "t": lambda key: translate(key, language),
                "account": actor,
                "csrf": auth.csrf(actor["csrf_seed"]),
                "users": service.users(q, offset),
                "pending": service.users(q=q, approval="PENDING"),
                "offset": offset,
                "metrics": service.metrics(),
                "history": service.history(),
            },
        )

    @api.get("/admin/projects", include_in_schema=False)
    def project_page(
        request: Request, q: str = Query("", max_length=200), offset: int = Query(0, ge=0)
    ):
        return templates.TemplateResponse(
            request=request,
            name="admin_projects.html",
            context={
                "prefix": prefix,
                "locale": locale(request.scope["auth_locale"]),
                "account": require_admin(),
                "projects": service.projects(q, offset),
                "offset": offset,
            },
        )

    @api.post("/admin/users/{identity}/review", include_in_schema=False)
    async def review_html(request: Request, identity: str):
        form = validate(AccessReview, await data(request))
        await run_in_threadpool(service.review, identity, form.decision)
        return RedirectResponse(prefix + "/admin", 303)

    @api.post("/admin/users/{identity}/delete", include_in_schema=False)
    async def delete_html(request: Request, identity: str):
        form = validate(DeleteAccount, await data(request))
        await run_in_threadpool(service.delete_account, identity, form.confirm_email)
        return RedirectResponse(prefix + "/admin", 303)

    @api.post("/admin/projects/{identity}/delete", include_in_schema=False)
    async def project_delete_html(request: Request, identity: str):
        if await data(request):
            raise ServiceError("invalid_form", 422)
        await run_in_threadpool(service.delete_project, identity)
        return RedirectResponse(prefix + "/admin/projects", 303)

    @api.post("/admin/users/{identity}", include_in_schema=False)
    async def change_html(request: Request, identity: str):
        values = await data(request)
        if values == {"operation": "revoke"}:
            await run_in_threadpool(service.revoke, identity)
        else:
            await run_in_threadpool(service.change, identity, validate(AdminChange, values))
        return RedirectResponse(prefix + "/admin", 303)

    return api
