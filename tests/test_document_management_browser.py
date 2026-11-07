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


def test_dashboard_project_delete_and_bulk_document_delete_keep_lifetime_history(design_server):
    from playwright.sync_api import expect, sync_playwright

    base, _, _, _ = design_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page()
        browser_login(page, base)
        # Create a queued/completed project through the authenticated HTTP API.
        created = page.evaluate("""async () => {
          const prefix = document.querySelector('meta[name=app-prefix]').content;
          const identity = await (await fetch(prefix+'/api/auth/session')).json();
          const form = new FormData(); form.set('language','es'); form.append('entities','DISEASE');
          form.append('files',new File(['abc'],'synthetic-bulk.txt',{type:'text/plain'}));
          const response = await fetch(prefix+'/api/jobs',{method:'POST',body:form,headers:{'X-CSRF-Token':identity.csrf_token}});
          if (!response.ok) throw new Error(await response.text());
          return response.json();
        }""")
        page.reload()
        remove = page.locator(f'[data-delete-project="{created["job_id"]}"]')
        expect(remove).to_be_visible()
        uploaded = page.locator("[data-upload-total]").inner_text()
        remove.click()
        page.get_by_role("dialog").get_by_role("button", name="Delete", exact=True).click()
        expect(page.locator(f'[data-delete-project="{created["job_id"]}"]')).to_have_count(0)
        expect(page.locator("[data-upload-total]")).to_have_text(uploaded)
        page.goto(base + "/documents?lang=en")
        page.get_by_role("button", name="Delete all documents", exact=True).click()
        page.get_by_role("dialog").get_by_role("button", name="Delete", exact=True).click()
        expect(page.locator("#management-message")).to_have_text(
            "Document content deleted. Upload history retained."
        )
        expect(page.locator("[data-document-usage]")).to_have_text("0 / 100")
        expect(page.locator("#document-history button")).to_have_count(0)
        expect(page.locator("[data-upload-total]")).to_have_text(uploaded)
        browser.close()


def test_select_documents_across_pages_refresh_cancel_and_delete(design_server):
    import json
    from pathlib import Path

    from playwright.sync_api import expect, sync_playwright

    base, _, _, _ = design_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        browser_login(page, base)
        page.evaluate("""async () => {
          const prefix=document.querySelector('meta[name=app-prefix]').content;
          const identity=await (await fetch(prefix+'/api/auth/session')).json();
          const form=new FormData();form.set('language','es');form.set('entities','DISEASE');
          for(let i=0;i<52;i++)form.append('files',new File(['abc'],`selection-${i}.txt`,{type:'text/plain'}));
          const response=await fetch(prefix+'/api/jobs',{method:'POST',body:form,headers:{'X-CSRF-Token':identity.csrf_token}});
          if(!response.ok)throw new Error(await response.text());
        }""")
        page.goto(base + "/documents?lang=en")
        page.locator("#document-filter").select_option("STORED")
        expect(page.locator("[data-select-document]")).to_have_count(50)
        before = int(page.locator("[data-document-usage]").inner_text().split("/")[0])
        total_uploaded = page.locator("[data-upload-total]").inner_text()
        expect(page.locator("#delete-selected-documents")).to_be_hidden()
        page.locator("[data-select-document]").nth(0).check()
        page.locator("[data-select-document]").nth(1).check()
        expect(page.locator("#document-selection-count")).to_have_text("2 selected")
        page.locator("#refresh-documents").click()
        expect(page.locator("[data-select-document]:checked")).to_have_count(2)
        page.locator("#delete-selected-documents").click()
        expect(page.get_by_role("dialog")).to_contain_text("Delete selected documents (2)")
        page.get_by_role("dialog").get_by_role("button", name="Close", exact=True).click()
        expect(page.locator("[data-document-usage]")).to_contain_text(str(before) + " /")
        page.locator("#documents-next").click()
        expect(page.locator("[data-select-document]")).to_have_count(before - 50)
        page.locator("[data-select-document]").first.check()
        expect(page.locator("#document-selection-count")).to_have_text("3 selected")
        if os.environ.get("AXE_CORE_PATH"):
            page.evaluate(Path(os.environ["AXE_CORE_PATH"]).read_text())
            result = page.evaluate(
                """async()=>await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})"""
            )
            assert not result["violations"], result["violations"]
            if output := os.environ.get("AXE_REPORT"):
                with Path(output).open("a") as target:
                    target.write(
                        json.dumps(
                            {
                                "screen": "Document multiselection",
                                "viewport": page.viewport_size,
                                "violations": [],
                                "incomplete_rules": [row["id"] for row in result["incomplete"]],
                            }
                        )
                        + "\n"
                    )
        page.locator("#delete-selected-documents").click()
        page.get_by_role("dialog").get_by_role("button", name="Delete", exact=True).click()
        expect(page.locator("#management-message")).to_have_text(
            "Document content deleted. Upload history retained."
        )
        expect(page.locator("[data-document-usage]")).to_contain_text(str(before - 3) + " /")
        expect(page.locator("[data-upload-total]")).to_have_text(total_uploaded)
        expect(page.locator("#delete-selected-documents")).to_be_hidden()
        for width in (375, 1440, 3840):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors
        browser.close()
