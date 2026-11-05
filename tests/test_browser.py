"""Real Chromium DOM checks. Availability is controlled by catalog HTTP fixtures only."""

import json
import os
from pathlib import Path

import pytest

from tests.test_viewer_browser import viewer_server as viewer_server


@pytest.mark.skipif(
    os.environ.get("BROWSER_TESTS") != "1", reason="Set BROWSER_TESTS=1 with local server on :8000"
)
@pytest.mark.parametrize(
    "viewport",
    [{"width": width, "height": 900} for width in (320, 375, 390, 768, 1024, 1440, 1920, 2560)],
)
def test_dynamic_form(viewport, viewer_server):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"]
        )
        page = browser.new_page(viewport=viewport)
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.route(
            "**/api/models",
            lambda route: route.fulfill(
                content_type="application/json",
                body=json.dumps(
                    [
                        {
                            "language": "es",
                            "entity": "DISEASE",
                            "display_name": "Diseases",
                            "available": True,
                        },
                        {
                            "language": "es",
                            "entity": "SYMPTOM",
                            "display_name": "Symptoms",
                            "available": True,
                        },
                        {
                            "language": "en",
                            "entity": "DISEASE",
                            "display_name": "Diseases",
                            "available": False,
                        },
                    ]
                ),
            ),
        )
        page.goto(viewer_server[0] + "/")
        page.wait_for_selector('#entities input[value="SYMPTOM"]')
        assert page.locator("#entities input:checked").count() == 2
        page.locator("#files").set_input_files(
            {"name": "a.txt", "mimeType": "text/plain", "buffer": b"Cancer."}
        )
        assert page.locator("#submit").is_enabled()
        page.select_option("#language", "en")
        assert page.locator("#entities input").is_disabled()
        assert page.locator("#submit").is_disabled()
        page.select_option("#language", "es")
        page.locator('#entities input[value="DISEASE"]').uncheck()
        assert page.locator("#entities input:checked").count() == 1
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        if os.environ.get("SCREENSHOT_OUTPUT") and viewport["width"] in (390, 1440):
            destination = Path(os.environ["SCREENSHOT_OUTPUT"])
            destination.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(destination / f"home-{viewport['width']}.png"), full_page=True)
        assert not errors
        browser.close()
