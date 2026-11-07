"""Progress remains visible within a batch, independently of publication counters."""

import json
import os
from pathlib import Path

import pytest

from tests.auth_helpers import browser_login
from tests.test_design_browser import design_server as design_server
from tests.test_design_browser import launch

pytestmark = pytest.mark.skipif(
    os.environ.get("BROWSER_TESTS") != "1", reason="Actual Chromium opt-in"
)


def test_live_models_liveness_and_index_stages(design_server):
    from playwright.sync_api import expect, sync_playwright

    base, _, job, _ = design_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def scan(phase):
            if not os.environ.get("AXE_CORE_PATH"):
                return
            page.evaluate(Path(os.environ["AXE_CORE_PATH"]).read_text())
            result = page.evaluate("""async () => await axe.run(document, {
              runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}
            })""")
            assert not result["violations"], result["violations"]
            if output := os.environ.get("AXE_REPORT"):
                with Path(output).open("a") as target:
                    target.write(
                        json.dumps(
                            {
                                "screen": "Model progress / " + phase,
                                "prefix": "/ner" if base.endswith("/ner") else "",
                                "viewport": page.viewport_size,
                                "axe_version": result["testEngine"]["version"],
                                "violations": [],
                                "incomplete_rules": [row["id"] for row in result["incomplete"]],
                            }
                        )
                        + "\n"
                    )

        browser_login(page, base)
        data = page.request.get(base + "/api/jobs/" + job["job_id"] + "/progress").json()
        data.update(
            status="QUEUED",
            stage="QUEUED",
            expires_at=None,
            annotated_documents=0,
            inference_percent=0,
            progress_percent=0,
            queue_position=1,
            pending_documents=2,
            processing_documents=0,
            worker={"available": False, "state": "unavailable"},
            models=[],
        )
        model = {
            "model_id": "synthetic-ner",
            "kind": "NER",
            "status": "RUNNING",
            "stage": "INFERENCE",
            "completed_documents": 0,
            "failed_documents": 0,
            "total_documents": 2,
            "batch_index": 1,
            "batch_count": 1,
            "completed_units": 1,
            "total_units": 4,
            "unit": "windows",
            "progress_percent": 25,
        }
        page.route("**/api/jobs/*/progress", lambda route: route.fulfill(json=data))
        page.goto(base + "/jobs/" + job["job_id"] + "?lang=en")
        expect(page.locator(".worker-unavailable")).to_contain_text("Start the worker")
        scan("worker unavailable")
        data.update(
            status="PROCESSING",
            stage="INFERENCE",
            pending_documents=0,
            processing_documents=2,
            worker={"available": True, "state": "busy"},
            models=[model],
            inference_percent=25,
        )
        expect(page.locator(".model-progress-card")).to_have_count(1)
        card = page.locator('[data-model-id="synthetic-ner"]')
        expect(card).to_contain_text("Windows: 1 / 4")
        expect(card.locator("progress")).to_have_attribute("value", "25")
        expect(page.locator(".global-progress > progress")).to_have_attribute("value", "25")
        expect(page.locator(".global-progress")).to_contain_text("0 / 2 annotated")
        normalizer = {
            **model,
            "model_id": "synthetic-normalizer",
            "kind": "NORMALIZATION",
            "stage": "BUILDING_INDEX",
            "unit": "terms",
            "total_units": 20,
            "completed_units": 5,
        }
        model.update(status="COMPLETED", completed_documents=2, progress_percent=100)
        data.update(stage="NORMALIZATION", inference_percent=100)
        data["models"].append(normalizer)
        expect(page.locator('[data-model-id="synthetic-normalizer"]')).to_contain_text(
            "Building terminology index"
        )
        expect(page.locator('[data-model-id="synthetic-normalizer"]')).to_contain_text(
            "Terms: 5 / 20"
        )
        scan("NER and FAISS")
        # Responsive cards never force horizontal scrolling on phones or 4k.
        for width in (375, 1440, 3840):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if output := os.environ.get("SCREENSHOT_OUTPUT"):
            directory = Path(output)
            directory.mkdir(parents=True, exist_ok=True)
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.screenshot(
                path=str(
                    directory
                    / (
                        "model-progress-prefix.png"
                        if base.endswith("/ner")
                        else "model-progress.png"
                    )
                ),
                full_page=True,
            )
        page.unroute("**/api/jobs/*/progress")
        page.reload()
        expect(page.locator("#statistics")).to_be_visible()
        if output:
            page.screenshot(
                path=str(
                    directory
                    / ("job-actions-prefix.png" if base.endswith("/ner") else "job-actions.png")
                ),
                full_page=True,
            )
        assert not errors
        browser.close()


def test_viewer_opens_raw_then_updates_ner_and_normalization_without_reload(design_server):
    import copy

    from playwright.sync_api import expect, sync_playwright

    base, _, job, _ = design_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        browser_login(page, base)
        api = base + "/api/jobs/" + job["job_id"]
        documents = page.request.get(api + "/documents").json()
        document = next(row for row in documents["items"] if row["annotation_count"])
        doc_api = api + "/documents/" + document["document_id"]
        text = page.request.get(doc_api).json()["text"]
        annotations = page.request.get(doc_api + "/annotations").json()["items"]
        progress = page.request.get(api + "/progress").json()
        progress.update(
            status="PROCESSING",
            stage="INFERENCE",
            expires_at=None,
            annotated_documents=0,
            partial_results=True,
            publication_revision=1,
        )
        state = {"phase": 0}

        def progress_response(route):
            route.fulfill(json={**progress, "publication_revision": state["phase"] + 1})

        def documents_response(route):
            row = {
                **document,
                "status": "PROCESSING",
                "updated_at": state["phase"] + 1,
                "annotation_count": len(annotations) if state["phase"] else 0,
            }
            route.fulfill(json={"items": [row], "total": 1, "offset": 0, "limit": 50})

        def annotations_response(route):
            rows = copy.deepcopy(annotations) if state["phase"] else []
            if state["phase"] == 2:
                for row in rows:
                    row["normalization"] = {
                        "code": "SYNTHETIC-123",
                        "term": "Synthetic concept",
                        "score": 1,
                        "language": "en",
                        "requested_language": "en",
                        "fallback_to_english": False,
                        "method": "exact",
                        "model": None,
                        "max_length": None,
                        "candidates": [],
                        "references": [],
                        "gazetteer_sha256": "synthetic",
                    }
            route.fulfill(
                json={
                    "items": rows,
                    "total": len(rows),
                    "offset": 0,
                    "limit": 500,
                    "revision": str(state["phase"]),
                }
            )

        page.route("**/api/jobs/*/progress", progress_response)
        page.route("**/api/jobs/*/documents?*", documents_response)
        page.route("**/api/jobs/*/documents/*/annotations?*", annotations_response)
        page.goto(base + "/jobs/" + job["job_id"] + "/viewer?lang=en")
        expect(page.locator("#annotated-text")).to_have_text(text)
        expect(page.locator("#document-list button").first).to_be_enabled()
        expect(page.locator("#annotation-list button")).to_have_count(0)
        state["phase"] = 1
        expect(page.locator("#annotation-list button")).to_have_count(
            len(annotations), timeout=10000
        )
        page.locator("#text-search").fill("Severe")
        page.locator("#annotation-list button").first.click()
        state["phase"] = 2
        expect(page.locator("#annotation-details")).to_contain_text("SYNTHETIC-123", timeout=10000)
        expect(page.locator("#text-search")).to_have_value("Severe")
        expect(page.locator("#annotated-text")).to_have_text(text)
        assert not errors
        browser.close()


def test_real_html_viewer_and_dashboard_allow_zero_finished_documents(design_server):
    import sqlite3

    from playwright.sync_api import expect, sync_playwright

    base, root, job, _ = design_server
    identity = job["job_id"]
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        browser_login(page, base)
        with sqlite3.connect(root / "jobs.sqlite3") as connection:
            original = connection.execute(
                "SELECT status,stage,processed_documents FROM jobs WHERE id=?", (identity,)
            ).fetchone()
            documents = connection.execute(
                "SELECT document_id,status FROM documents WHERE job_id=?", (identity,)
            ).fetchall()
            connection.execute(
                "UPDATE jobs SET status='PROCESSING',stage='INFERENCE',processed_documents=0 WHERE id=?",
                (identity,),
            )
            connection.execute(
                "UPDATE documents SET status='PROCESSING' WHERE job_id=?", (identity,)
            )
        try:
            progress = page.request.get(base + "/api/jobs/" + identity + "/progress").json()
            assert progress["annotated_documents"] == 0 and progress["partial_results"]
            page.goto(base + "/?lang=en")
            link = page.locator(f'a[href$="/jobs/{identity}/viewer?lang=en"]')
            expect(link).to_be_visible()
            link.click()
            expect(page.locator("#annotated-text")).not_to_be_empty()
            expect(page.locator("#annotation-list button").first).to_be_visible()
            response = page.goto(base + "/api/jobs/" + identity + "/viewer?lang=en")
            assert response.status == 200
            expect(page.locator("#annotated-text")).not_to_be_empty()
        finally:
            browser.close()
            with sqlite3.connect(root / "jobs.sqlite3") as connection:
                connection.execute(
                    "UPDATE jobs SET status=?,stage=?,processed_documents=? WHERE id=?",
                    (*original, identity),
                )
                connection.executemany(
                    "UPDATE documents SET status=? WHERE job_id=? AND document_id=?",
                    [(status, identity, document) for document, status in documents],
                )
