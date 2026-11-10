"""Generate a complete relative-route security matrix without opening production data."""

import tempfile
from pathlib import Path

from app.auth.middleware import AUTH_PAGES, PUBLIC_API, PUBLIC_ASSETS
from app.config import Settings
from app.main import create_app


def routes(app):
    def walk(items, prefix=""):
        for route in items:
            if hasattr(route, "original_router"):
                yield from walk(
                    route.original_router.routes,
                    prefix + getattr(route.include_context, "prefix", ""),
                )
            elif getattr(route, "path", None) is not None:
                methods = getattr(route, "methods", None) or {"GET", "HEAD"}
                for method in sorted(methods):
                    yield method, prefix + route.path

    return sorted(set(walk(app.routes)))


def policy(path, method):
    if path in PUBLIC_ASSETS or path in ("/health", "/ready"):
        return "Public minimal", "None", "No job data", "anonymous sweep"
    if path in AUTH_PAGES or path in PUBLIC_API:
        return (
            "Public authentication",
            "CSRF for writes; throttle; validated fields",
            "One-use verifier for account actions",
            "auth_v4 + real browser",
        )
    if path == "/static":
        return (
            "Session except exact public auth assets",
            "No storage mount",
            "No job files",
            "anonymous sweep + browser",
        )
    if path.startswith(("/api/admin/", "/admin")):
        return (
            "Session",
            "Approved live ADMIN + MFA; atomic revalidation for writes; CSRF",
            "All account and project data; audited account/project erasure",
            "admin_workflows + real browser + revocation/upload races",
        )
    if path in (
        "/api/my/documents",
        "/api/my/documents/delete",
        "/api/my/document-usage",
        "/documents",
    ):
        return (
            "Session",
            "Approved live owner; ADMIN + MFA for an explicit foreign project; CSRF writes",
            "Personal quota/history; authorized foreign-project metadata",
            "individual/bulk deletion + two-user history + browser",
        )
    if path.startswith(("/api/jobs/", "/jobs/")):
        return (
            "Session",
            "Owner or approved ADMIN + MFA, centrally and in service; expiry; CSRF writes",
            "Owner data; authorized administrators can inspect and delete",
            "two-user isolation + admin all-project API/browser + legacy/TTL",
        )
    if path in ("/api/jobs", "/annotate"):
        return (
            "Session",
            "Approved account; optional email verification; CSRF for POST; current custom quota atomically",
            "Owner from session only",
            "quota + unverified + delayed-upload tests",
        )
    if path in ("/docs", "/openapi.json"):
        return "Session", "Authenticated schema access", "No clinical contents", "anonymous sweep"
    if path in ("/", "/dashboard", "/api/my/jobs", "/my-jobs"):
        return (
            "Session",
            "Own account and owner-filtered history",
            "SQL owner filter; no foreign queue counts",
            "two-user history + anonymous sweep",
        )
    if path in ("/api/models", "/api/languages"):
        return (
            "Session",
            "Authenticated shared model metadata",
            "No job data",
            "catalog + anonymous sweep",
        )
    return (
        "Session",
        "Own account/session only; CSRF for writes",
        "Identity from live session; allowlisted fields",
        "auth lifecycle + anonymous sweep",
    )


def main():
    with tempfile.TemporaryDirectory() as root:
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                cookie_secure=False,
                mail_backend="memory",
                storage_root=Path(root),
                public_base_url="http://testserver",
            )
        )
        lines = [
            "# V4 route security inventory",
            "",
            "Relative routes; APP_PREFIX is prepended uniformly, including /ner. Anonymous HTML requests redirect303 to login; private APIs/OpenAPI return401. All state-changing requests require CSRF and origin checks. Methods not explicitly routed never bypass the gate.",
            "",
            "Public assets: "
            + ", ".join(sorted(PUBLIC_ASSETS))
            + ". No data/storage directory is mounted publicly.",
            "",
            "| Method | Route | Authentication | Authorization policy | Ownership | Coverage |",
            "|---|---|---|---|---|---|",
        ]
        for method, path in routes(app):
            values = policy(path, method)
            lines.append("| " + " | ".join((method, path, *values)) + " |")
        Path("docs/ROUTE_SECURITY_V4.md").write_text("\n".join(lines) + "\n")
        print(f"Inventoried {len(routes(app))} method/route pairs")


if __name__ == "__main__":
    main()
