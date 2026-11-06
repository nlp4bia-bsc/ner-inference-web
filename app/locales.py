"""Interface languages; independent of the document/model language inventory."""

import json
from functools import lru_cache
from pathlib import Path

LOCALES = {
    "en": "English",
    "es": "Español",
    "ca": "Català",
    "cs": "Čeština",
    "da": "Dansk",
    "de": "Deutsch",
    "el": "Ελληνικά",
    "et": "Eesti",
    "fr": "Français",
    "it": "Italiano",
    "nl": "Nederlands",
    "no": "Norsk",
    "pt": "Português",
    "ro": "Română",
    "ru": "Русский",
    "sv": "Svenska",
}
CODES = tuple(LOCALES)


@lru_cache
def catalog(language):
    path = Path(__file__).parent / "translations" / f"{language}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def translated(english, language):
    return catalog(language).get(english, english)
