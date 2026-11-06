"""Explicit public origin, with a narrow local-development loopback alias pair."""

from urllib.parse import urlsplit

LOOPBACK_HOSTS = {"localhost", "127.0.0.1"}


def http_origin(value):
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        return (
            parsed.scheme,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
    except (ValueError, TypeError):
        return None


def trusted_origin(value, settings):
    candidate, expected = http_origin(value), http_origin(settings.public_base_url)
    if candidate is None or expected is None:
        return False
    if candidate == expected:
        return True
    return (
        settings.app_env in ("development", "test")
        and not settings.cookie_secure
        and candidate[1] in LOOPBACK_HOSTS
        and expected[1] in LOOPBACK_HOSTS
        and (candidate[0], candidate[2]) == (expected[0], expected[2])
    )


def safe_origin(value):
    if not value:
        return "missing"
    if value == "null":
        return "null"
    parsed = http_origin(value)
    if parsed is None:
        return "invalid"
    scheme, hostname, port = parsed
    # Keep request diagnostics bounded; never log credentials, paths or queries.
    return f"{scheme}://{hostname[:253]}:{port}"
