import json
import os

import pytest

from tests.test_viewer_browser import viewer_server as viewer_server

pytestmark = pytest.mark.skipif(
    os.environ.get("BROWSER_TESTS") != "1", reason="Opt in browser tests"
)


def launch(p):
    return p.chromium.launch(
        executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
        headless=True,
        args=["--no-sandbox"],
    )


def test_paste_mode_counters_and_acceptance_dialog(viewer_server):
    from playwright.sync_api import sync_playwright

    base, _ = viewer_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.route(
            "**/api/models",
            lambda route: route.fulfill(
                content_type="application/json",
                body=json.dumps(
                    [
                        {
                            "language": "es",
                            "entity": "DISEASE",
                            "display_name": "Disease",
                            "available": True,
                        }
                    ]
                ),
            ),
        )
        page.route(
            "**/api/jobs",
            lambda route: route.fulfill(
                status=202,
                content_type="application/json",
                body=json.dumps(
                    {
                        "job_id": "test",
                        "status": "QUEUED",
                        "token": "test",
                        "url": base + "/jobs/test",
                    }
                ),
            ),
        )
        page.goto(base + "/")
        page.wait_for_selector("#entities input")
        page.get_by_role("tab", name="Paste text").click()
        page.locator("#pasted-text").fill("😀 abc\n漢字")
        assert "8 characters" in page.locator("#paste-counter").text_content()
        page.locator("#name").fill("Test")
        page.locator("#email").fill("test@example.org")
        page.locator("#submit").click()
        page.wait_for_selector("dialog[open]")
        assert "Request accepted" in page.locator("dialog").text_content()
        assert "Copy private link" in page.locator("dialog").text_content()
        browser.close()


def test_progress_collapse_completion_and_clock_skew(viewer_server):
    from playwright.sync_api import sync_playwright

    base, token = viewer_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 375, "height": 812})
        page.add_init_script(
            "const ActualDate=Date;window.Date=class extends ActualDate {static now(){return ActualDate.now()+365*86400000;}};"
        )
        counter = {"value": 0}

        def progress(route):
            counter["value"] += 1
            done = counter["value"] > 1
            data = {
                "status": "COMPLETED" if done else "PROCESSING",
                "stage": "COMPLETED" if done else "INFERENCE",
                "total_documents": 2,
                "annotated_documents": 2 if done else 1,
                "processing_documents": 0 if done else 1,
                "failed_documents": 0,
                "pending_documents": 0,
                "progress_percent": 100 if done else 50,
                "updated_at": "2026-11-05T12:00:00Z",
                "server_now": "2026-11-05T12:00:00Z",
                "expires_at": "2026-11-08T12:00:00Z" if done else None,
                "queue_position": None,
            }
            route.fulfill(content_type="application/json", body=json.dumps(data))

        page.route("**/progress", progress)
        page.goto(base + "/jobs/" + token)
        page.wait_for_function(
            "() => document.querySelector('.global-progress progress')?.value===50"
        )
        page.locator(".global-progress summary").click()
        assert not page.locator(".global-progress").get_attribute("open")
        page.wait_for_selector("dialog[open]")
        assert "Annotations ready" in page.locator("dialog").text_content()
        page.get_by_role("button", name="Close", exact=True).click()
        page.locator(".global-progress summary").click()
        assert (
            "2 days" in page.locator(".countdown").text_content()
            or "3 days" in page.locator(".countdown").text_content()
        )
        assert "Scheduled deletion" in page.locator(".countdown").text_content()
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        browser.close()


def test_table_selection_and_document_tree(viewer_server):
    from playwright.sync_api import sync_playwright

    base, token = viewer_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page()
        page.goto(base + "/jobs/" + token + "/viewer")
        page.wait_for_selector("#annotation-list button")
        assert page.locator("#document-list details summary").first.text_content() == "nested"
        page.locator(".annotation-table-wrap summary").click()
        page.locator("#annotation-table-body button").first.click()
        assert page.locator("#annotation-table-body tr[aria-selected=true]").count() == 1
        assert page.locator(".annotated.selected").count() > 0
        assert page.locator("#individual-ann").get_attribute("href").endswith("/download/ann")
        browser.close()


def test_expiry_clears_text_table_and_individual_downloads(viewer_server):
    from playwright.sync_api import sync_playwright

    base, token = viewer_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page()
        payload = {
            "status": "COMPLETED",
            "stage": "COMPLETED",
            "total_documents": 2,
            "annotated_documents": 2,
            "processing_documents": 0,
            "failed_documents": 0,
            "pending_documents": 0,
            "progress_percent": 100,
            "updated_at": "2026-11-05T12:00:00Z",
            "server_now": "2026-11-05T12:00:00Z",
            "expires_at": "2026-11-05T12:00:03Z",
            "queue_position": None,
            "mentions": 7,
            "provisional_statistics": {},
            "partial_results": False,
        }
        page.route(
            "**/progress",
            lambda route: route.fulfill(content_type="application/json", body=json.dumps(payload)),
        )
        page.goto(base + "/jobs/" + token + "/viewer")
        page.wait_for_selector("#annotation-list button")
        page.wait_for_function(
            "() => document.querySelector('#viewer-status').textContent.includes('expired')"
        )
        assert page.locator("#annotated-text").text_content() == ""
        assert page.locator("#annotation-table-body").text_content() == ""
        assert page.locator("#annotation-details").text_content() == ""
        assert page.locator("#individual-ann").get_attribute("href") is None
        browser.close()
