"""Print safe effective configuration and where it came from; never mutate settings."""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from dotenv import dotenv_values

import app
from app.auth.origins import trusted_origin
from app.config import Settings
from app.services.runtime import inference_dependencies
from app.services.worker_status import worker_status

SAFE_FIELDS = (
    "app_env",
    "public_base_url",
    "app_prefix",
    "cookie_secure",
    "require_email_verification",
    "mail_backend",
    "model_loading_mode",
    "hf_hub_offline",
)


def origin(value):
    parsed = urlsplit(value)
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


def processing_status(settings):
    path = settings.db_path.resolve()
    result = {"database": str(path), "exists": path.is_file()}
    if not result["exists"]:
        return {**result, "state": "unavailable", "available": False}
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            return {**result, **worker_status(SimpleNamespace(connect=lambda: connection))}
        finally:
            connection.close()
    except sqlite3.Error:
        return {**result, "state": "unavailable", "available": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--expect-origin", help="Browser origin, e.g. http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    if args.expect_origin:
        try:
            parsed = urlsplit(args.expect_origin)
            origin(args.expect_origin)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path not in ("", "/")
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError()
        except ValueError:
            parser.error("--expect-origin requires only an HTTP(S) scheme, hostname and port")
    env_file = args.env_file.resolve()
    settings = Settings(_env_file=env_file)
    shell = {key.lower(): value for key, value in os.environ.items() if value}
    file_values = {key.lower(): value for key, value in dotenv_values(env_file).items() if value}
    result = {
        "python_executable": sys.executable,
        "working_directory": str(Path.cwd()),
        "application_directory": str(Path(app.__file__).resolve().parent),
        "env_file": {"path": str(env_file), "exists": env_file.is_file()},
        "settings": {
            key.upper(): {
                "value": getattr(settings, key),
                "source": "environment"
                if key in shell
                else ".env"
                if key in file_values
                else "default",
            }
            for key in SAFE_FIELDS
        },
        "inference_dependencies": inference_dependencies(),
        "processing_service": processing_status(settings),
    }
    if args.expect_origin:
        result["origin_matches"] = trusted_origin(args.expect_origin, settings)
    print(json.dumps(result, indent=2))
    return 1 if result.get("origin_matches") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
