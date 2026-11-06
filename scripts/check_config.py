"""Print safe effective configuration and where it came from; never mutate settings."""

import argparse
import json
import os
import sys
from importlib.util import find_spec
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

import app
from app.config import Settings

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
        "inference_dependencies": {
            name: find_spec(name) is not None
            for name in ("torch", "transformers", "huggingface_hub", "lab")
        },
    }
    if args.expect_origin:
        result["origin_matches"] = origin(settings.public_base_url) == origin(args.expect_origin)
    print(json.dumps(result, indent=2))
    return 1 if result.get("origin_matches") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
