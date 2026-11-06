"""The owner can remove content from the document manager and see live quota."""

import os

import pytest

from tests.auth_helpers import browser_login
from tests.test_design_browser import design_server as design_server
from tests.test_design_browser import launch

pytestmark = pytest.mark.skipif(
    os.environ.get("BROWSER_TESTS") != "1", reason="Actual Chromium opt-in"
)


def test_document_manager_deletion_refreshes_quota_and_keeps_history(design_server):
    from playwright.sync_api import expect, sync_playwright

    base, _, job, _ = design_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        browser_login(page, base)
        page.goto(base + "/documents?job=" + job["job_id"] + "&lang=en")
        row = page.locator("#document-history tr").first
        expect(row).to_be_visible()
        total_before = page.locator("[data-upload-total]").inner_text()
        occupied_before = int(
            page.locator("[data-document-usage]").inner_text().split("/")[0].strip()
        )
        row.get_by_role("button", name="Delete document", exact=True).click()
        page.get_by_role("dialog").get_by_role("button", name="Delete", exact=True).click()
        expect(page.locator("#management-message")).to_have_text(
            "Document content deleted. Upload history retained."
        )
        expect(page.locator("[data-document-usage]")).to_contain_text(
            str(occupied_before - 1) + " /"
        )
        expect(page.locator("[data-upload-total]")).to_have_text(total_before)
        page.locator("#document-filter").select_option("DELETED")
        expect(page.locator("#document-history tr")).to_have_count(1)
        expect(page.locator("#document-history button")).to_have_count(0)
        browser.close()
