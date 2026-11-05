"""Presentation context only; authorization remains in middleware and services."""

from datetime import datetime, timezone

from app.auth.i18n import locale
from app.ui_i18n import translate


def context(request):
    language = locale(request.scope.get("auth_locale"))
    account = request.scope.get("auth_user")
    return {
        "ui_locale": language,
        "u": lambda key, **values: translate(key, language, **values),
        "ui_account": account,
        "ui_csrf": request.app.state.auth.csrf(account["csrf_seed"]) if account else "",
        "ui_version": request.app.version,
        "ui_date": lambda value: (
            datetime.fromtimestamp(value, timezone.utc).isoformat() if value else "—"
        ),
    }
