"""Real administrator approval, account/project erasure and role-specific presentation."""

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.config import Settings
from app.users.schemas import Register
from scripts.create_admin import create_admin
from tests.auth_helpers import PASSWORD
from tests.test_auth_browser import login, signup, submit_job
from tests.test_design_browser import launch
from tests.test_simple_registration import simple_server as simple_server

pytestmark = pytest.mark.skipif(
    os.environ.get("BROWSER_TESTS") != "1", reason="Actual Chromium opt-in"
)


def bootstrap(root, base):
    settings = Settings(
        _env_file=None,
        storage_root=root,
        app_env="test",
        cookie_secure=False,
        public_base_url=base,
        app_prefix=urlsplit(base).path,
        require_email_verification=False,
        mail_backend="none",
    )
    return create_admin(
        settings,
        Register(
            full_name="Synthetic Administrator",
            email="browser-admin@example.test",
            institution="Synthetic Institute",
            professional_role="RESEARCHER",
            password=PASSWORD,
            password_confirmation=PASSWORD,
            legal_accepted=True,
        ),
    )


def administrator_login(page, base):
    login(page, base, "browser-admin@example.test")
    assert page.locator("#otp").count() == 0
    assert page.locator('a[href*="/mfa"]').count() == 0
    assert page.request.get(base + "/mfa").status == 404


def confirm(page):
    from playwright.sync_api import expect

    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Confirm", exact=True).click()
    expect(dialog).to_be_hidden()


def check_screen(page, name):
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), page.url
    if os.environ.get("SCREENSHOT_OUTPUT"):
        folder = Path(os.environ["SCREENSHOT_OUTPUT"])
        folder.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(folder / (name + "-" + str(page.viewport_size["width"]) + ".png")),
            full_page=True,
        )
    if os.environ.get("AXE_CORE_PATH"):
        page.evaluate(Path(os.environ["AXE_CORE_PATH"]).read_text())
        results = page.evaluate(
            """async()=>await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})"""
        )
        assert not results["violations"], [
            {"id": v["id"], "nodes": [n["failureSummary"] for n in v["nodes"]]}
            for v in results["violations"]
        ]


@pytest.mark.parametrize("width", [390, 1440])
def test_admin_reviews_manages_quota_views_foreign_projects_and_erases_account(
    simple_server, tmp_path, width
):
    from playwright.sync_api import expect, sync_playwright

    base = simple_server
    bootstrap(tmp_path / "private", base)
    with sync_playwright() as p:
        browser = launch(p)
        user_context = browser.new_context(viewport={"width": width, "height": 1000})
        admin_context = browser.new_context(viewport={"width": width, "height": 1000})
        user, admin = user_context.new_page(), admin_context.new_page()
        signup(user, base, "applicant@example.test")
        expect(user.get_by_role("status")).to_contain_text("awaiting administrator approval")
        user.goto(base + "/login")
        user.locator("#email").fill("applicant@example.test")
        user.locator("#password").fill(PASSWORD)
        user.get_by_role("button", name="Sign in", exact=True).click()
        expect(user.get_by_role("status")).to_contain_text("awaiting administrator approval")
        assert user.request.get(base + "/api/admin/users").status == 401
        administrator_login(admin, base)
        expect(admin.locator("body")).to_have_class(re.compile(r"\badmin-theme\b"))
        admin.goto(base + "/admin")
        card = admin.locator("[data-request-user]").filter(has_text="applicant@example.test")
        expect(card).to_contain_text("Synthetic University")
        identity = card.get_attribute("data-request-user")
        check_screen(admin, "admin-pending")
        card.get_by_role("button", name="Approve", exact=True).click()
        confirm(admin)
        expect(admin.locator(f'[data-request-user="{identity}"]')).to_have_count(0)
        login(user, base, "applicant@example.test")
        expect(user.locator("body")).not_to_have_class(re.compile(r"\badmin-theme\b"))
        assert user.request.get(base + "/admin/projects?role=ADMIN").status == 403
        accepted = submit_job(user, base, "abc")
        user.goto(base + "/jobs/" + accepted["job_id"] + "/viewer")
        user.locator('[data-reader-mode="towers"]').click()
        disease_color = "rgb(240, 166, 198)"
        expect(user.locator(".tower-tag").first).to_have_css("fill", disease_color)
        admin.goto(base + "/admin/projects")
        expect(admin.locator(f'[data-admin-project="{accepted["job_id"]}"]')).to_contain_text(
            "applicant@example.test"
        )
        check_screen(admin, "admin-projects")
        admin.goto(base + "/jobs/" + accepted["job_id"] + "/viewer")
        expect(admin.locator("body")).to_have_class(re.compile(r"\badmin-theme\b"))
        admin.locator('[data-reader-mode="towers"]').click()
        # The live viewer can redraw a tower between finding its SVG and reading
        # computed style. Retry against the current node, including the exact
        # reference color, rather than reading a detached node's empty style.
        expect(admin.locator(".tower-tag").first).to_have_css("fill", disease_color)
        check_screen(admin, "admin-viewer")
        admin.goto(base + "/documents?job=" + accepted["job_id"])
        expect(admin.locator("#document-history")).to_contain_text("pasted-text.txt")
        expect(admin.locator("h1")).to_have_text("Documents")
        expect(admin.locator(".notice").first).to_contain_text("applicant@example.test")
        admin.goto(base + "/admin")
        row = admin.locator(f'[data-account-user="{identity}"]')
        row.locator('input[name="document_limit"]').fill("0")
        row.locator(".admin-change button").click()
        expect(admin.get_by_role("dialog")).to_contain_text("0")
        confirm(admin)
        assert user.request.get(base + "/api/my/document-usage").json()["limit"] == 0
        assert user.request.get(base + "/api/jobs/" + accepted["job_id"]).status == 200
        row = admin.locator(f'[data-account-user="{identity}"]')
        row.locator('input[name="document_limit"]').fill("5")
        row.locator(".admin-change button").click()
        confirm(admin)
        assert user.request.get(base + "/api/my/document-usage").json()["limit"] == 5
        admin.goto(base + "/annotate")
        expect(admin.locator("body")).to_have_class(re.compile(r"\badmin-theme\b"))
        check_screen(admin, "admin-annotation")
        admin.goto(base + "/admin/projects")
        admin.locator("details.card > summary").click()
        admin.locator(f'[data-admin-project="{accepted["job_id"]}"]').get_by_role(
            "button", name="Delete project", exact=True
        ).click()
        expect(admin.get_by_role("dialog")).to_contain_text("all its documents and annotations")
        confirm(admin)
        expect(admin.locator(f'[data-admin-project="{accepted["job_id"]}"]')).to_have_count(0)
        assert user.request.get(base + "/api/my/document-usage").json()["occupied"] == 0
        admin.goto(base + "/admin")
        admin.locator(f'[data-account-user="{identity}"]').get_by_role(
            "button", name="Delete account", exact=True
        ).click()
        expect(admin.get_by_role("dialog")).to_contain_text("cannot be undone")
        confirm(admin)
        expect(admin.locator(f'[data-account-user="{identity}"]')).to_have_count(0)
        assert user.request.get(base + "/api/profile").status == 401
        browser.close()


def test_decline_and_admin_mobile_pages_are_guarded_and_readable(simple_server, tmp_path):
    from playwright.sync_api import expect, sync_playwright

    base = simple_server
    bootstrap(tmp_path / "private", base)
    with sync_playwright() as p:
        browser = launch(p)
        user = browser.new_page(viewport={"width": 320, "height": 900})
        admin = browser.new_page(viewport={"width": 320, "height": 900})
        signup(user, base, "declined-browser@example.test")
        administrator_login(admin, base)
        admin.goto(base + "/admin")
        card = admin.locator("[data-request-user]").filter(has_text="declined-browser@example.test")
        card.get_by_role("button", name="Decline", exact=True).click()
        confirm(admin)
        check_screen(admin, "admin-mobile")
        for path in ("/admin/projects", "/annotate", "/documents"):
            admin.goto(base + path)
            expect(admin.locator("body")).to_have_class(re.compile(r"\badmin-theme\b"))
            check_screen(admin, "admin-mobile-" + path.replace("/", "-"))
        user.goto(base + "/login")
        user.locator("#email").fill("declined-browser@example.test")
        user.locator("#password").fill(PASSWORD)
        user.get_by_role("button", name="Sign in", exact=True).click()
        expect(user.get_by_role("status")).to_contain_text("declined")
        assert user.request.get(base + "/api/admin/projects").status == 401
        admin.goto(base + "/admin?lang=es")
        expect(admin.locator("h1")).to_have_text("Gestión de usuarios")
        check_screen(admin, "admin-es")
        browser.close()
