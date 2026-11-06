"""Presentation context only; authorization remains in middleware and services."""

from datetime import datetime, timezone

from app.auth.i18n import locale
from app.locales import LOCALES
from app.ui_i18n import translate


def context(request):
    language = locale(request.scope.get("auth_locale"))
    account = request.scope.get("auth_user")
    return {
        "ui_locale": language,
        "ui_locales": LOCALES.items(),
        "u": lambda key, **values: translate(key, language, **values),
        "ui_account": account,
        "document_quota": request.app.state.jobs.quota() if account else None,
        "ui_csrf": request.app.state.auth.csrf(account["csrf_seed"]) if account else "",
        "ui_version": request.app.version,
        "email_verification_required": request.app.state.settings.require_email_verification,
        "support_email": request.app.state.settings.support_email,
        "mail_available": request.app.state.mailer.configured,
        "ui_date": lambda value: (
            datetime.fromtimestamp(value, timezone.utc).isoformat() if value else "—"
        ),
    }
