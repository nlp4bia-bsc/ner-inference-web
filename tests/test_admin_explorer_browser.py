"""Real lazy tree navigation, exact deep links, exports and confirmed foreign erasure."""

import os
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from app.config import Settings
from app.main import create_app
from tests.admin_explorer_fixtures import publish_known_results
from tests.test_admin_browser import administrator_login, bootstrap, check_screen
from tests.test_auth_browser import login, signup, submit_job
from tests.test_design_browser import launch
from tests.test_simple_registration import simple_server as simple_server

pytestmark = pytest.mark.skipif(
    os.environ.get("BROWSER_TESTS") != "1", reason="Actual Chromium opt-in"
)


def statistic(page, key, value):
    expect(page.locator(f'#explorer-statistics [data-statistic="{key}"] dd')).to_have_text(
        str(value)
    )


@pytest.mark.parametrize("simple_server", ["", "/annotation-tool"], indirect=True)
@pytest.mark.parametrize("width", [320, 1440])
def test_lazy_tree_annotations_existing_viewer_exports_and_delete(simple_server, tmp_path, width):
    base = simple_server
    root = tmp_path / "private"
    bootstrap(root, base)
    with sync_playwright() as p:
        browser = launch(p)
        admin_context = browser.new_context(viewport={"width": width, "height": 1000})
        owner_context = browser.new_context(viewport={"width": width, "height": 1000})
        admin, owner = admin_context.new_page(), owner_context.new_page()
        signup(owner, base, "tree-browser@example.test")
        administrator_login(admin, base)
        admin.goto(base + "/admin")
        card = admin.locator("[data-request-user]").filter(has_text="tree-browser@example.test")
        user_id = card.get_attribute("data-request-user")
        card.get_by_role("button", name="Approve", exact=True).click()
        admin.get_by_role("dialog").get_by_role("button", name="Confirm", exact=True).click()
        expect(admin.locator(f'[data-request-user="{user_id}"]')).to_have_count(0)
        login(owner, base, "tree-browser@example.test")
        accepted = submit_job(owner, base, "abc")
        settings = Settings(
            _env_file=None,
            app_env="test",
            cookie_secure=False,
            public_base_url=base,
            app_prefix=urlsplit(base).path,
            storage_root=root,
            mail_backend="none",
        )
        app = create_app(settings)
        documents = publish_known_results(app, accepted)
        job_id, document_id = accepted["job_id"], documents[0]["document_id"]
        requests = []
        admin.on("request", lambda request: requests.append(request.url))
        admin.goto(base + "/admin/projects")
        statistic(admin, "annotations", 3)
        assert not any("/explorer/users/" in url or "/annotations?" in url for url in requests)
        user_node = admin.locator(f'details[data-explorer-node="user:{user_id}"]')
        summary = user_node.locator(":scope > summary")
        summary.focus()
        summary.press("Enter")
        project = admin.locator(f'details[data-explorer-node="project:{job_id}"]')
        expect(project).to_be_visible()
        assert not any(f"/explorer/projects/{job_id}" in url for url in requests)
        project.locator(":scope > summary").click()
        document = admin.locator(f'details[data-explorer-node="document:{job_id}:{document_id}"]')
        expect(document).to_be_visible()
        assert not any("/annotations?" in url for url in requests)
        document.locator(":scope > summary").click()
        expect(document.locator("tbody")).to_contain_text("MEDICATION")
        expect(document.locator("tbody")).to_contain_text("Synthetic concept")
        expect(document.locator("tbody")).to_contain_text("[1, 3)")
        expect(document.locator("tbody")).to_contain_text("A, B")
        check_screen(admin, "admin-tree-expanded")
        with admin.expect_download() as download:
            document.get_by_role("link", name="Download TXT", exact=True).click()
        assert open(download.value.path(), "rb").read() == b"abc"
        brat = project.get_by_role("link", name="Download BRAT", exact=True)
        assert admin.request.get(brat.get_attribute("href")).status == 200
        assert (
            "MEDICATION"
            in admin.request.get(
                project.get_by_role("link", name="Download TSV", exact=True).get_attribute("href")
            ).text()
        )
        # Existing viewer receives the selected document, overlap and normalization.
        viewer = admin_context.new_page()
        viewer.goto(
            document.get_by_role("link", name="Open viewer", exact=True).get_attribute("href")
        )
        expect(viewer.locator("#filename")).to_have_text(documents[0]["filename"])
        expect(viewer.locator("#annotated-text")).to_contain_text("abc")
        viewer.locator('[data-reader-mode="towers"]').click()
        expect(viewer.locator(".tower-tag")).to_have_count(3)
        viewer.locator("#annotation-list button").filter(has_text="MEDICATION").click()
        expect(viewer.locator("#annotation-details")).to_contain_text("C123")
        assert owner.request.get(base + "/api/admin/explorer/statistics").status == 403
        document.get_by_role("button", name="Delete document", exact=True).click()
        expect(admin.get_by_role("dialog")).to_contain_text(documents[0]["filename"])
        admin.get_by_role("dialog").get_by_role("button", name="Close", exact=True).click()
        assert owner.request.get(base + "/api/my/document-usage").json()["occupied"] == 1
        document.get_by_role("button", name="Delete document", exact=True).click()
        admin.get_by_role("dialog").get_by_role("button", name="Delete", exact=True).click()
        statistic(admin, "documents", 0)
        statistic(admin, "annotations", 0)
        assert owner.request.get(base + "/api/my/document-usage").json()["occupied"] == 0
        events = admin.request.get(base + "/api/admin/audit").json()
        assert any(
            event["action"] == "ADMIN_PROJECT_DOCUMENTS_DELETED"
            and document_id in event["details"]["document_ids"]
            for event in events
        )
        browser.close()


@pytest.mark.parametrize("simple_server", ["", "/annotation-tool"], indirect=True)
def test_viewer_deep_link_opens_a_nonfirst_document_and_tree_restores_after_refresh(
    simple_server, tmp_path
):
    base, root = simple_server, tmp_path / "private"
    bootstrap(root, base)
    with sync_playwright() as p:
        browser = launch(p)
        admin = browser.new_page(viewport={"width": 1440, "height": 1000})
        administrator_login(admin, base)
        # Reuse actual admission and the test server's real synthetic worker.
        session = admin.request.get(base + "/api/auth/session").json()
        import io
        import time
        import zipfile

        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("a.txt", "first document")
            archive.writestr("z.txt", "second target document")
        response = admin.request.post(
            base + "/api/jobs",
            headers={"X-CSRF-Token": session["csrf_token"]},
            multipart={
                "language": "es",
                "entities": "DISEASE",
                "files": {
                    "name": "corpus.zip",
                    "mimeType": "application/zip",
                    "buffer": stream.getvalue(),
                },
            },
        )
        assert response.status == 202, response.text()
        accepted = response.json()
        for _ in range(100):
            status = admin.request.get(base + "/api/jobs/" + accepted["job_id"]).json()
            if status["status"] == "COMPLETED":
                break
            time.sleep(0.05)
        assert status["status"] == "COMPLETED"
        docs = admin.request.get(base + f"/api/jobs/{accepted['job_id']}/documents").json()["items"]
        target = next(row for row in docs if row["filename"] == "z.txt")
        metadata_requests = []

        def delayed_metadata(route):
            metadata_requests.append(route.request.url)
            # Refresh while the deep-link initialization is still in flight.
            admin.locator("#document-search").dispatch_event("input")
            admin.wait_for_timeout(350)
            route.continue_()

        admin.route(f"**/documents/{target['document_id']}?limit=1", delayed_metadata)
        admin.goto(base + f"/jobs/{accepted['job_id']}/viewer?document={target['document_id']}")
        expect(admin.locator("#filename")).to_have_text("z.txt")
        expect(admin.locator("#annotated-text")).to_contain_text("second target document")
        assert len(metadata_requests) == 1
        admin.unroute(f"**/documents/{target['document_id']}?limit=1", delayed_metadata)
        admin.goto(base + "/admin/projects")
        user_id = session["user"]["id"]
        user_node = admin.locator(f'details[data-explorer-node="user:{user_id}"]')
        user_node.locator(":scope > summary").click()
        project = admin.locator(f'details[data-explorer-node="project:{accepted["job_id"]}"]')
        project.locator(":scope > summary").click()
        expect(project.locator('[data-explorer-node^="document:"]')).to_have_count(2)
        admin.get_by_role("button", name="Refresh", exact=True).click()
        expect(
            admin.locator(f'details[data-explorer-node="project:{accepted["job_id"]}"]')
        ).to_have_attribute("open", "")
        expect(
            admin.locator(
                f'details[data-explorer-node="project:{accepted["job_id"]}"] [data-explorer-node^="document:"]'
            )
        ).to_have_count(2)
        # Lazy disclosure can collapse and expand with the keyboard without navigation.
        root_summary = admin.locator("#admin-explorer-tree > details > summary")
        root_summary.focus()
        root_summary.press("Space")
        expect(user_node).not_to_be_visible()
        root_summary.press("Space")
        expect(user_node).to_be_visible()
        browser.close()


@pytest.mark.parametrize("simple_server", ["/annotation-tool"], indirect=True)
def test_expiry_clears_loaded_tree_annotations_even_with_browser_clock_skew(
    simple_server, tmp_path
):
    import time

    base, root = simple_server, tmp_path / "private"
    bootstrap(root, base)
    with sync_playwright() as p:
        browser = launch(p)
        admin = browser.new_page(viewport={"width": 1440, "height": 1000})
        administrator_login(admin, base)
        accepted = submit_job(admin, base, "abc")
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                cookie_secure=False,
                public_base_url=base,
                app_prefix="/annotation-tool",
                storage_root=root,
                mail_backend="none",
            )
        )
        docs = publish_known_results(app, accepted)
        with app.state.db.connect() as c:
            c.execute(
                "UPDATE jobs SET expires_at=? WHERE id=?", (time.time() + 5, accepted["job_id"])
            )
        session = admin.request.get(base + "/api/auth/session").json()
        admin.add_init_script("Date.now = () => 0")
        admin.goto(base + "/admin/projects")
        admin.locator(
            f'details[data-explorer-node="user:{session["user"]["id"]}"] > summary'
        ).click()
        project = admin.locator(f'details[data-explorer-node="project:{accepted["job_id"]}"]')
        project.locator(":scope > summary").click()
        document = project.locator(
            f'details[data-explorer-node="document:{accepted["job_id"]}:{docs[0]["document_id"]}"]'
        )
        document.locator(":scope > summary").click()
        expect(document.locator("tbody")).to_contain_text("Synthetic concept")
        expect(admin.locator("#admin-explorer-tree")).not_to_contain_text(
            "Synthetic concept", timeout=12000
        )
        statistic(admin, "annotations", 0)
        expect(admin.locator("#admin-explorer-tree")).to_contain_text("Results have expired.")
        project = admin.locator(f'details[data-explorer-node="project:{accepted["job_id"]}"]')
        project.get_by_role("button", name="Delete project", exact=True).click()
        expect(admin.get_by_role("dialog")).to_contain_text(accepted["job_id"])
        admin.get_by_role("dialog").get_by_role("button", name="Delete", exact=True).click()
        statistic(admin, "expired_projects", 0)
        expect(
            admin.locator(f'details[data-explorer-node="project:{accepted["job_id"]}"]')
        ).to_have_count(0)
        browser.close()
