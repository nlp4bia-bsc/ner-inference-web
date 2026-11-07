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
