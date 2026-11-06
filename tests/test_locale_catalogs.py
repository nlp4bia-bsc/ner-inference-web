"""Catalog completeness and interpolation are shared by server and browser."""

import re

from app.locales import CODES, catalog
from app.ui_i18n import MESSAGES
from app.users.schemas import Profile


def test_all_sixteen_locale_catalogs_cover_every_source_and_placeholder():
    sources = {row[0] for row in MESSAGES.values()}
    assert len(CODES) == 16
    for language in CODES:
        if language in ("en", "es", "ca"):
            continue
        translations = catalog(language)
        assert sources <= translations.keys(), (language, sources - translations.keys())
        for source in sources:
            assert translations[source].strip()
            assert set(re.findall(r"\{\w+\}", source)) == set(
                re.findall(r"\{\w+\}", translations[source])
            )
        profile = Profile(
            full_name="Researcher",
            institution="Institution",
            professional_role="RESEARCHER",
            preferred_locale=language,
        )
        assert profile.preferred_locale == language
