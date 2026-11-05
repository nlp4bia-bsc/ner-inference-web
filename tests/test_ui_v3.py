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
        from tests.auth_helpers import browser_login

        browser_login(page, viewer_server[0])
        page.goto(base + "/annotate")
        page.wait_for_selector("#entities input", state="attached")
        page.locator('[data-category="DISEASE"] > summary').click()
        page.locator('#entities input[value="DISEASE"]').check()
        page.get_by_role("tab", name="Paste text").click()
        page.locator("#pasted-text").fill("😀 abc\n漢字")
        assert "8 characters" in page.locator("#paste-counter").text_content()
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
        from tests.auth_helpers import browser_login

        browser_login(page, viewer_server[0])
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
        from tests.auth_helpers import browser_login

        browser_login(page, viewer_server[0])
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
        from tests.auth_helpers import browser_login

        browser_login(page, viewer_server[0])
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


def test_flat_catalog_explicit_multi_selection_and_multilingual_choice(viewer_server):
    from playwright.sync_api import sync_playwright

    base, _ = viewer_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        active = {
            "bsc-bio-ehr-es-distemist",
            "bsc-bio-ehr-es-carmen-distemist",
            "DT4H_XLM-R_stl_multilingual_disease",
        }

        def catalog(route):
            response = route.fetch()
            rows = response.json()
            for row in rows:
                row["available"] = row.get("model_id") in active
            route.fulfill(response=response, json=rows)

        page.route("**/api/models", catalog)
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
        from tests.auth_helpers import browser_login

        browser_login(page, viewer_server[0])
        page.goto(base + "/annotate")
        page.wait_for_selector(".model-category")
        assert page.locator(".model-category").count() == 13
        assert page.locator('[data-category="LOCATION"]').count() == 1
        assert page.locator('[data-category="PROFESSION"]').count() == 1
        assert page.locator("#entities input:checked").count() == 0
        page.locator('[data-category="DISEASE"] > summary').click()
        assert page.locator("#entities input:checked").count() == 0
        for identity in active:
            page.locator(f'#entities input[value="{identity}"]').check()
        assert "3 active" in page.locator('[data-category="DISEASE"] > summary').text_content()
        assert (
            page.locator('#entities input[value="DT4H_XLM-R_mtl_multilingual_multilabel"]').count()
            == 1
        )
        assert not page.locator('#entities input[value="GPE_NOM"]').count()
        assert not page.get_by_text("Other entity types", exact=True).count()
        page.get_by_role("tab", name="Paste text").click()
        page.locator("#pasted-text").fill("Madrid")
        with page.expect_request("**/api/jobs") as sent:
            page.locator("#submit").click()
        body = sent.value.post_data
        assert body.count('name="models"') == 3
        assert all(identity in body for identity in active)
        assert 'name="entities"' not in body
        page.wait_for_selector("dialog[open]")
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        browser.close()


@pytest.mark.parametrize("width", [375, 1440])
def test_annotation_provenance_is_visible_in_inspector_and_mobile_sheet(viewer_server, width):
    from playwright.sync_api import sync_playwright

    base, token = viewer_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": width, "height": 900})

        def annotate(route):
            response = route.fetch()
            data = response.json()
            for row in data["items"]:
                if row["id"] == "T2":
                    row.update(
                        model_ids=["detector-a", "detector-b"],
                        original_labels=["GPE_NOM", "FAC_NOM"],
                        sources=[
                            {
                                "model_id": "detector-a",
                                "model_version": "v1",
                                "original_label": "GPE_NOM",
                                "score": 0.7,
                            },
                            {
                                "model_id": "detector-b",
                                "model_version": "v2",
                                "original_label": "FAC_NOM",
                                "score": 0.9,
                            },
                        ],
                    )
            route.fulfill(response=response, json=data)

        page.route("**/annotations?*", annotate)
        from tests.auth_helpers import browser_login

        browser_login(page, viewer_server[0])
        page.goto(base + "/jobs/" + token + "/viewer")
        page.wait_for_selector('[data-table-annotation="T2"]', state="attached")
        page.locator(".annotation-table-wrap summary").click()
        page.locator('[data-table-annotation="T2"] button').click()
        assert "detector-a" in page.locator("#annotation-details").text_content()
        assert "FAC_NOM" in page.locator("#annotation-details").text_content()
        assert "0.7" in page.locator("#annotation-details").text_content()
        if width == 375:
            page.locator("#entity-sheet-trigger").click()
            assert "detector-b" in page.locator("dialog[open]").text_content()
            assert "GPE_NOM" in page.locator("dialog[open]").text_content()
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        browser.close()
