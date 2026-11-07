"""Real browser reflow/interaction checks; all accounts and annotations are synthetic."""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tests.auth_helpers import DEFAULT_EMAIL, PASSWORD, browser_login
from tests.test_auth_browser import login, signup, verify

pytestmark = pytest.mark.skipif(
    os.environ.get("BROWSER_TESTS") != "1", reason="Actual Chromium opt-in"
)
VIEWPORTS = [
    (320, 640),
    (375, 812),
    (390, 844),
    (768, 1024),
    (1024, 768),
    (1440, 900),
    (1920, 1080),
    (2560, 1440),
]


@pytest.fixture(scope="module", params=["", "/ner"])
def design_server(tmp_path_factory, request):
    import pyotp
    from playwright.sync_api import sync_playwright

    from app.config import Settings
    from app.users.schemas import Register
    from scripts.create_admin import create_admin
    from tests.viewer_fixtures import seed_viewer

    root = tmp_path_factory.mktemp("design-web")
    with socket.socket() as socket_:
        socket_.bind(("127.0.0.1", 0))
        port = socket_.getsockname()[1]
    base = f"http://127.0.0.1:{port}" + request.param
    settings = Settings(
        _env_file=None,
        storage_root=root / "private",
        app_env="test",
        cookie_secure=False,
        mail_backend="memory",
        model_loading_mode="validated_local",
        require_email_verification=True,
        app_prefix=request.param,
        public_base_url=base,
        min_free_disk_mb=0,
    )
    _, accepted, _, _ = seed_viewer(settings)
    create_admin(
        settings.model_copy(update={"mail_backend": "file"}),
        Register(
            full_name="Synthetic Administrator",
            email="design-admin@example.test",
            institution="Synthetic Research Institute",
            professional_role="RESEARCHER",
            password=PASSWORD,
            password_confirmation=PASSWORD,
            legal_accepted=True,
        ),
    )
    env = {
        **os.environ,
        "APP_ENV": "test",
        "COOKIE_SECURE": "false",
        "MAIL_BACKEND": "file",
        "MODEL_LOADING_MODE": "validated_local",
        "REQUIRE_EMAIL_VERIFICATION": "true",
        "STORAGE_ROOT": str(settings.storage_root),
        "PUBLIC_BASE_URL": base,
        "APP_PREFIX": request.param,
        "AUTH_RATE_EMAIL_ATTEMPTS": "300",
        "AUTH_RATE_IP_ATTEMPTS": "1000",
        "TEST_PREDICTOR_DELAY_SECONDS": "1",
        "RATE_LIMIT_SECONDS": "1",
        "MIN_FREE_DISK_MB": "0",
    }
    with (root / "server.log").open("w") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.auth_browser_server:factory",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + "/health", timeout=0.2)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("Synthetic design server did not start")
            with sync_playwright() as p:
                browser = launch(p)
                page = browser.new_page()
                verify(page, settings.storage_root, "design-admin@example.test")
                login(page, base, "design-admin@example.test")
                page.goto(base + "/mfa")
                page.locator("#current_password").fill(PASSWORD)
                page.get_by_role("button", name="Set up authenticator", exact=True).click()
                secret = page.locator("#mfa-secret").text_content()
                page.locator("#otp").fill(pyotp.TOTP(secret).at(time.time() + 30))
                page.get_by_role("button", name="Confirm authenticator code", exact=True).click()
                page.locator("#recovery-codes").wait_for()
                codes = iter(page.locator("#recovery-codes li").all_text_contents())
                browser.close()
            yield base, settings.storage_root, accepted, codes
        finally:
            server.terminate()
            server.wait(timeout=10)


def launch(p):
    return p.chromium.launch(
        executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
        headless=True,
        args=["--no-sandbox"],
    )


def reflow(page):
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), page.url
    logo = page.locator(".bsc-logo img")
    logo.scroll_into_view_if_needed()
    page.wait_for_function(
        "() => { const img=document.querySelector('.bsc-logo img');return img.complete && img.naturalWidth>0; }"
    )
    page.evaluate("window.scrollTo(0,0)")
    bounds = logo.bounding_box()
    assert abs(bounds["width"] / bounds["height"] - 283.46 / 69.36) < 0.03
    assert page.locator("h1").count() == 1
    if page.viewport_size["width"] in (390, 1440) and os.environ.get("AXE_CORE_PATH"):
        page.evaluate(Path(os.environ["AXE_CORE_PATH"]).read_text())
        result = page.evaluate("""async () => await axe.run(document, {
          runOnly: {type:'tag', values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}
        })""")
        assert not result["violations"], [
            {"rule": row["id"], "nodes": [node["target"] for node in row["nodes"]]}
            for row in result["violations"]
        ]
        if os.environ.get("AXE_REPORT"):
            with Path(os.environ["AXE_REPORT"]).open("a") as output:
                import json

                output.write(
                    json.dumps(
                        {
                            "screen": page.locator("h1").inner_text(),
                            "viewport": page.viewport_size,
                            "locale": page.locator("html").get_attribute("lang"),
                            "axe_version": result["testEngine"]["version"],
                            "passes": len(result["passes"]),
                            "violations": [],
                            "incomplete_rules": [row["id"] for row in result["incomplete"]],
                            "incomplete_targets": {
                                row["id"]: [node["target"] for node in row["nodes"]]
                                for row in result["incomplete"]
                            },
                        }
                    )
                    + "\n"
                )
    # Keyboard targets are neither clipped nor outside the horizontal viewport.
    for box in page.locator("button:visible,input:visible,select:visible").evaluate_all(
        "(nodes)=>nodes.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,right:r.right,width:r.width}})"
    ):
        assert (
            box["x"] >= -1 and box["right"] <= page.viewport_size["width"] + 1 and box["width"] > 0
        )


def capture(page, name, width, prefix):
    if not os.environ.get("SCREENSHOT_OUTPUT") or width not in (390, 1440):
        return
    folder = Path(os.environ["SCREENSHOT_OUTPUT"])
    folder.mkdir(parents=True, exist_ok=True)
    suffix = ("-prefix" if prefix else "") + ("-mobile" if width == 390 else "-desktop")
    page.screenshot(path=str(folder / (name + suffix + ".png")), full_page=True)
    if name == "dashboard":
        page.locator(".site-footer").screenshot(path=str(folder / ("footer" + suffix + ".png")))


@pytest.mark.parametrize("viewport", VIEWPORTS)
def test_all_screens_reflow_locales_navigation_and_controls(design_server, viewport):
    from playwright.sync_api import expect, sync_playwright

    from tests.viewer_fixtures import TEXT

    base, root, job, codes = design_server
    width, height = viewport
    prefix = base.endswith("/ner")
    with sync_playwright() as p:
        browser = launch(p)
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/login")
        reflow(page)
        capture(page, "login", width, prefix)
        page.locator("#password").fill(PASSWORD)
        page.get_by_role("button", name="Show password", exact=True).click()
        assert page.locator("#password").get_attribute("type") == "text"
        page.get_by_role("button", name="Hide password", exact=True).click()
        page.locator("#password").fill("")
        page.locator("#auth-locale").select_option("ca")
        expect(page.locator("h1")).to_have_text("Inicia la sessió")
        page.goto(base + "/register?lang=en")
        reflow(page)
        if width <= 760:
            expect(page.locator("#profession-caption")).to_have_text(
                "Clinician / Healthcare Professional"
            )
            expect(page.locator("#profession-caption")).to_be_visible()
        capture(page, "register", width, prefix)
        page.select_option("#professional_role", "OTHER")
        expect(page.locator("#professional_role_other")).to_be_visible()
        browser_login(page, base)
        reflow(page)
        capture(page, "dashboard", width, prefix)
        assert page.locator(".jobs-table tbody tr").count() >= 1
        if page.locator("#menu-toggle").is_visible():
            page.locator("#menu-toggle").click()
            expect(page.locator("#primary-navigation")).to_be_visible()
            page.keyboard.press("Escape")
            expect(page.locator("#menu-toggle")).to_have_attribute("aria-expanded", "false")
        assert page.locator('#primary-navigation a[href*="/admin"]').count() == 0
        for path, name in [
            ("/my-jobs", "jobs"),
            ("/models", "models"),
            ("/profile", "profile"),
            ("/sessions", "sessions"),
            ("/account-deletion", "deletion"),
        ]:
            page.goto(base + path + "?lang=en")
            reflow(page)
            capture(page, name, width, prefix)
        page.goto(base + "/account-deletion")
        page.get_by_role("button", name="Request account deletion", exact=True).click()
        expect(page.get_by_role("dialog")).to_be_visible()
        assert page.get_by_role("dialog").bounding_box()["width"] <= width
        page.get_by_role("button", name="Close", exact=True).click()
        page.goto(base + "/annotate?lang=en")
        page.locator('[data-category="DISEASE"] > summary').click()
        page.locator('input[name="models"][value="es-disease"]').check()
        page.locator("#files").set_input_files(
            {
                "name": "synthetic.txt",
                "mimeType": "text/plain",
                "buffer": b"Synthetic research example.",
            }
        )
        page.locator("#auth-locale").select_option("es")
        assert page.locator("#files").evaluate("(input)=>input.files.length") == 1
        assert page.locator('input[name="models"][value="es-disease"]').is_checked()
        assert page.locator("#language").input_value() == "es"
        page.locator("#auth-locale").select_option("en")
        reflow(page)
        capture(page, "annotation", width, prefix)
        page.goto(base + "/models")
        page.locator('[data-category="DISEASE"] > summary').click()
        reflow(page)
        capture(page, "catalog-expanded", width, prefix)
        page.goto(base + "/jobs/" + job["job_id"] + "/viewer?lang=en")
        page.wait_for_selector("#annotation-list button")
        assert page.locator("#annotated-text").text_content() == TEXT
        page.locator('[data-count="4"]').first.focus()
        page.keyboard.press("Enter")
        assert page.locator("#region-annotations button").count() == 4
        page.locator(".annotation-table-wrap summary").click()
        page.select_option("#model-filter", "synthetic-test-only")
        assert page.locator("#annotation-list button").count() == 7
        page.locator("#annotation-list button").first.click()
        reflow(page)
        capture(page, "viewer", width, prefix)
        before = page.locator("#annotated-text").text_content()
        for language, title in [
            ("es", "Visor de anotaciones"),
            ("ca", "Visualitzador d'anotacions"),
        ]:
            page.locator("#auth-locale").select_option(language)
            expect(page.locator("h1")).to_have_text(title)
            assert page.locator("#annotated-text").text_content() == before
            assert page.locator("#model-filter").input_value() == "synthetic-test-only"
            reflow(page)
        page.locator("#auth-locale").select_option("en")
        if width <= 760:
            page.locator("#entity-sheet-trigger").click()
            expect(page.get_by_role("dialog")).to_be_visible()
            assert page.get_by_role("dialog").bounding_box()["width"] <= width
            page.get_by_role("button", name="Close", exact=True).click()
        if width == 1440:
            # Actual submission and real transition from queued/processing to completed.
            page.goto(base + "/annotate")
            page.locator('[data-category="DISEASE"] > summary').click()
            page.locator('input[name="models"][value="es-disease"]').check()
            page.get_by_role("tab", name="Paste text", exact=True).click()
            page.locator("#pasted-text").fill("Entirely synthetic research text.")
            page.locator("#submit").click()
            page.get_by_role("button", name="Continue to request", exact=True).click()
            page.get_by_role("dialog").wait_for(timeout=15000)
            expect(page.get_by_role("dialog")).to_contain_text("Annotations ready")
            capture(page, "completion-dialog", width, prefix)
            page.get_by_role("button", name="Close", exact=True).click()
        # An independent new account really registers/verifies and has an empty dashboard.
        empty = browser.new_context(viewport={"width": width, "height": height})
        empty_page = empty.new_page()
        email = f"empty-{width}@example.test"
        signup(empty_page, base, email)
        verify(empty_page, root, email)
        login(empty_page, base, email)
        expect(empty_page.locator(".empty-state")).to_contain_text(
            "Your research workspace is ready."
        )
        reflow(empty_page)
        capture(empty_page, "dashboard-empty", width, prefix)
        admin = browser.new_context(viewport={"width": width, "height": height})
        admin_page = admin.new_page()
        admin_page.goto(base + "/login")
        admin_page.locator("#email").fill("design-admin@example.test")
        admin_page.locator("#password").fill(PASSWORD)
        admin_page.locator("#otp").fill(next(codes))
        admin_page.get_by_role("button", name="Sign in", exact=True).click()
        admin_page.wait_for_url(base + "/?lang=en")
        admin_page.goto(base + "/admin")
        reflow(admin_page)
        capture(admin_page, "admin", width, prefix)
        row = admin_page.locator(".admin-table tbody tr").filter(has_text=DEFAULT_EMAIL)
        row.locator('select[name="access_tier"]').select_option("EXTENDED")
        row.get_by_role("button", name="Save changes", exact=True).click()
        expect(admin_page.get_by_role("dialog")).to_contain_text("EXTENDED")
        capture(admin_page, "admin-confirmation", width, prefix)
        admin_page.get_by_role("button", name="Close", exact=True).click()
        assert admin.request.get(base + "/api/profile").json()["system_role"] == "ADMIN"
        # Cancellation leaves the ordinary account tier unchanged.
        assert context.request.get(base + "/api/profile").json()["access_tier"] == "STANDARD"
        # Real server revocation clears the old view and presents the expiry state.
        identity = context.request.get(base + "/api/auth/session").json()
        assert (
            context.request.post(
                base + "/api/auth/logout", data={}, headers={"X-CSRF-Token": identity["csrf_token"]}
            ).status
            == 200
        )
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        page.wait_for_url(base + "/login?reason=expired&lang=en")
        expect(page.get_by_role("status")).to_contain_text("Session expired")
        capture(page, "session-expired", width, prefix)
        assert not errors
        browser.close()


def test_large_display_fonts_and_all_interface_languages(design_server):
    from playwright.sync_api import sync_playwright

    from app.locales import LOCALES

    base, _, _, _ = design_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(base + "/login")
        assert page.evaluate("getComputedStyle(document.documentElement).fontSize") == "18px"
        page.set_viewport_size({"width": 3840, "height": 2160})
        assert page.evaluate("getComputedStyle(document.documentElement).fontSize") == "24px"
        for code in LOCALES:
            page.goto(base + "/login?lang=" + code)
            assert page.locator("html").get_attribute("lang") == code
            assert page.locator("#auth-locale").input_value() == code
            assert page.locator("h1").inner_text().strip()
            reflow(page)
        page.goto(base + "/login?lang=en")
        page.locator("#email").fill(DEFAULT_EMAIL)
        page.locator("#password").fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_url(base + "/?lang=en")
        for code in LOCALES:
            page.goto(base + "/documents?lang=" + code)
            page.wait_for_selector("#document-history tr")
            assert page.locator("html").get_attribute("lang") == code
            reflow(page)
        browser.close()


def test_normalization_is_lexical_unless_bi_encoder_explicitly_checked(design_server):
    from email import policy
    from email.parser import BytesParser

    from playwright.sync_api import expect, sync_playwright

    base, _, _, _ = design_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        browser_login(page, base)
        page.goto(base + "/annotate?lang=en")
        page.locator("#normalization-options").wait_for(state="hidden")
        page.locator("#normalize").check()
        expect(page.locator("#normalization-method")).to_have_value("levenshtein")
        expect(page.locator("#normalization-lexical-method option:checked")).to_have_text(
            "Fuzzy match"
        )
        assert "levenshtein" not in page.locator("body").inner_text().lower()
        expect(page.locator("#normalization-threshold")).to_have_value("0.8")
        expect(page.locator("#use-bi-encoder")).not_to_be_checked()
        expect(page.locator("#bi-encoder-warning")).to_be_hidden()
        page.locator("#normalization-threshold").fill("0.87")
        page.locator("#use-bi-encoder").check()
        expect(page.locator("#normalization-method")).to_have_value("bi_encoder")
        expect(page.locator("#bi-encoder-warning")).to_be_visible()
        expect(page.locator("#normalization-threshold")).to_be_disabled()
        reflow(page)
        page.locator("#use-bi-encoder").uncheck()
        page.locator("#normalization-lexical-method").select_option("exact")
        expect(page.locator("#normalization-method")).to_have_value("exact")
        expect(page.locator("#normalization-threshold")).to_be_disabled()
        page.locator("#normalization-lexical-method").select_option("levenshtein")
        page.locator("#auth-locale").select_option("es")
        expect(page.locator("#normalization-threshold")).to_have_value("0.87")
        expect(page.locator("#normalization-method")).to_have_value("levenshtein")
        page.locator("#auth-locale").select_option("en")
        page.locator('[data-category="DISEASE"] > summary').click()
        page.locator('input[name="models"][value="es-disease"]').check()
        page.locator("#files").set_input_files(
            {"name": "synthetic.txt", "mimeType": "text/plain", "buffer": b"Synthetic."}
        )
        submitted = []

        def record(route):
            request = route.request
            message = BytesParser(policy=policy.default).parsebytes(
                b"Content-Type: "
                + request.headers["content-type"].encode()
                + b"\r\n\r\n"
                + request.post_data_buffer
            )
            submitted.append(
                {
                    part.get_param("name", header="content-disposition"): part.get_payload(
                        decode=True
                    )
                    for part in message.iter_parts()
                }
            )
            route.fulfill(status=202, json={"url": base + "/jobs/synthetic"})

        page.route("**/api/jobs", record)
        expect(page.locator("#summary")).to_contain_text("Fuzzy match")
        assert "levenshtein" not in page.locator("body").inner_text().lower()
        page.locator("#submit").click()
        expect(page.get_by_role("dialog")).to_be_visible()
        assert submitted[0]["normalization_method"] == b"levenshtein"
        assert submitted[0]["normalization_threshold"] == b"0.87"
        assert submitted[0]["normalize"] == b"true"
        browser.close()


def test_inspector_labels_and_values_do_not_overlap_in_any_locale(design_server):
    from playwright.sync_api import expect, sync_playwright

    from app.locales import LOCALES

    base, _, job, _ = design_server
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        browser_login(page, base)
        page.goto(base + "/jobs/" + job["job_id"] + "/viewer?lang=es")
        page.locator("#annotation-list button").first.click()
        expect(
            page.locator("#annotation-details dt").filter(has_text="Solapamientos")
        ).to_be_visible()
        reflow(page)
        for width in (320, 390, 1440, 1920, 3840):
            page.set_viewport_size({"width": width, "height": 1000})
            for code in LOCALES:
                page.select_option("#auth-locale", code)
                issues = page.locator("#annotation-details").evaluate("""panel => {
                  const list=panel.querySelector('dl');
                  const rects=node=>{const range=document.createRange();range.selectNodeContents(node);return [...range.getClientRects()].filter(r=>r.width&&r.height);};
                  const intersect=(a,b)=>a.left<b.right-.1&&a.right>b.left+.1&&a.top<b.bottom-.1&&a.bottom>b.top+.1;
                  return [...list.querySelectorAll('dt')].flatMap(label=>{
                    const value=label.nextElementSibling;
                    const overlap=rects(label).some(a=>rects(value).some(b=>intersect(a,b)));
                    return overlap||label.scrollWidth>label.clientWidth+1||value.scrollWidth>value.clientWidth+1
                      ? [{label:label.textContent,value:value.textContent,overlap}] : [];
                  });
                }""")
                assert not issues, (width, code, issues)
        browser.close()
