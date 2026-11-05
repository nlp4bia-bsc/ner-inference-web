from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from app.admin.service import AdminService
from app.auth.i18n import locale, translate
from app.auth.routes import data, validate
from app.errors import ServiceError
from app.permissions.policies import require_admin
from app.users.schemas import AdminChange


def router(db, settings, auth, templates):
    api = APIRouter(dependencies=[Depends(require_admin)])
    service = AdminService(db, settings)
    prefix = settings.app_prefix

    @api.get("/api/admin/users")
    def users(q: str = Query("", max_length=200), offset: int = Query(0, ge=0)):
        return service.users(q, offset)

    @api.patch("/api/admin/users/{identity}")
    async def change(identity: str, request: Request):
        form = validate(AdminChange, await data(request))
        service.change(identity, form)
        return {"message": translate("saved", request.scope["auth_locale"])}

    @api.post("/api/admin/users/{identity}/revoke-sessions")
    async def revoke(identity: str, request: Request):
        if await data(request):
            raise ServiceError("invalid_form", 422)
        service.revoke(identity)
        return {"message": translate("saved", request.scope["auth_locale"])}

    @api.get("/api/admin/metrics")
    def metrics():
        return service.metrics()

    @api.get("/api/admin/audit")
    def history(offset: int = Query(0, ge=0)):
        return service.history(offset)

    @api.get("/admin", include_in_schema=False)
    def page(request: Request, q: str = Query("", max_length=200)):
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
                "users": service.users(q),
                "metrics": service.metrics(),
                "history": service.history(),
            },
        )

    @api.post("/admin/users/{identity}", include_in_schema=False)
    async def change_html(request: Request, identity: str):
        values = await data(request)
        if values == {"operation": "revoke"}:
            service.revoke(identity)
        else:
            service.change(identity, validate(AdminChange, values))
        return RedirectResponse(prefix + "/admin", 303)

    return api
