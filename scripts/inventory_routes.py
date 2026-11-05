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
            "Session except auth.css/auth.js",
            "No storage mount",
            "No job files",
            "anonymous sweep + browser",
        )
    if path.startswith(("/api/admin/", "/admin")):
        return (
            "Session",
            "Live ADMIN + MFA; atomic revalidation for writes",
            "No clinical access",
            "admin/MFA tests + independent review",
        )
    if path.startswith(("/api/jobs/", "/jobs/")):
        return (
            "Session",
            "Central and service owner guard + expiry",
            "Strict owner only; ADMIN has no bypass",
            "two-user API/browser + legacy/TTL",
        )
    if path in ("/api/jobs", "/annotate"):
        return (
            "Session",
            "Verified email; CSRF for POST; account quota atomically",
            "Owner from session only",
            "quota + unverified + delayed-upload tests",
        )
    if path in ("/docs", "/openapi.json"):
        return "Session", "Authenticated schema access", "No clinical contents", "anonymous sweep"
    if path in ("/", "/dashboard", "/api/my/jobs"):
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
