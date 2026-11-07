"""Canonical terminology metadata, including UMLS LAT and ISO language aliases."""

import re
import unicodedata

from scripts.gazetteer_values import cell_values

# ISO 639-2 bibliographic/terminological forms and UMLS LAT codes.
LANGUAGE_ALIASES = {
    "spa": "es",
    "eng": "en",
    "cat": "ca",
    "cze": "cs",
    "ces": "cs",
    "dan": "da",
    "ger": "de",
    "deu": "de",
    "gre": "el",
    "ell": "el",
    "est": "et",
    "fre": "fr",
    "fra": "fr",
    "ita": "it",
    "dut": "nl",
    "nld": "nl",
    "nor": "no",
    "nob": "nb",
    "nno": "nn",
    "por": "pt",
    "rum": "ro",
    "ron": "ro",
    "rus": "ru",
    "swe": "sv",
    "pol": "pl",
    "fin": "fi",
    "hun": "hu",
    "slo": "sk",
    "slk": "sk",
    "slv": "sl",
    "hrv": "hr",
    "lit": "lt",
    "lav": "lv",
    "bul": "bg",
    "ukr": "uk",
    "tur": "tr",
    "ara": "ar",
    "jpn": "ja",
    "chi": "zh",
    "zho": "zh",
    "kor": "ko",
    "heb": "he",
    "lat": "la",
}
LANGUAGE_NAMES = {
    "spanish": "es",
    "espanol": "es",
    "castellano": "es",
    "english": "en",
    "catalan": "ca",
    "catala": "ca",
    "czech": "cs",
    "cestina": "cs",
    "danish": "da",
    "dansk": "da",
    "german": "de",
    "deutsch": "de",
    "greek": "el",
    "estonian": "et",
    "eesti": "et",
    "french": "fr",
    "francais": "fr",
    "italian": "it",
    "italiano": "it",
    "dutch": "nl",
    "nederlands": "nl",
    "norwegian": "no",
    "norsk": "no",
    "portuguese": "pt",
    "portugues": "pt",
    "romanian": "ro",
    "romana": "ro",
    "russian": "ru",
    "swedish": "sv",
    "svenska": "sv",
}


def metadata_token(value):
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value.strip().casefold())
        if not unicodedata.combining(char)
    )


def normalize_language(value):
    languages = set()
    try:
        entries = cell_values(value)
    except ValueError:
        return None
    for entry in entries:
        if entry is None:
            continue
        token = metadata_token(entry).replace("_", "-")
        language = LANGUAGE_NAMES.get(token) or LANGUAGE_ALIASES.get(token)
        if language is None:
            # Retain the language of a regional/script tag, never infer it from terms.
            base = token.split("-", 1)[0]
            if re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", token):
                language = LANGUAGE_ALIASES.get(base, base if len(base) == 2 else None)
        if language is None:
            return None
        languages.add(language)
    return languages.pop() if len(languages) == 1 else None


def normalize_entity(value, aliases):
    entities = set()
    try:
        entries = cell_values(value)
    except ValueError:
        return None
    for entry in entries:
        if entry is None:
            continue
        token = metadata_token(entry)
        entities.add(aliases.get(token, token.upper()))
    return entities.pop() if len(entities) == 1 else None


def normalize_series(series, normalizer):
    """Resolve repeated scalar labels once; list cells keep their explicit meaning."""
    try:
        lookup = {value: normalizer(value) for value in series.dropna().unique()}
        return series.map(lookup)
    except (TypeError, NotImplementedError):  # Arrow list metadata may not support unique().
        return series.map(normalizer)
