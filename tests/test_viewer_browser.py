import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("BROWSER_TESTS") != "1", reason="Opt in with BROWSER_TESTS=1"
)


@pytest.fixture(scope="module")
def viewer_server(tmp_path_factory):
    import urllib.request

    from app.config import Settings
    from tests.viewer_fixtures import seed_viewer

    root = tmp_path_factory.mktemp("viewer-web")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    s = Settings(
        storage_root=root / "storage",
        app_prefix="/ner",
        public_base_url=f"http://127.0.0.1:{port}/ner",
        app_env="test",
        cookie_secure=False,
        mail_backend="memory",
        model_loading_mode="validated_local",
        require_email_verification=True,
    )
    _, accepted, _, _ = seed_viewer(s)
    env = {
        **os.environ,
        "STORAGE_ROOT": str(s.storage_root),
        "APP_PREFIX": "/ner",
        "PUBLIC_BASE_URL": s.public_base_url,
        "APP_ENV": "test",
        "COOKIE_SECURE": "false",
        "MAIL_BACKEND": "file",
        "MODEL_LOADING_MODE": "validated_local",
        "REQUIRE_EMAIL_VERIFICATION": "true",
        "AUTH_RATE_EMAIL_ATTEMPTS": "100",
        "AUTH_RATE_IP_ATTEMPTS": "300",
    }
    with (root / "server.log").open("w") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.asgi:app",
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
                    urllib.request.urlopen(s.public_base_url + "/health", timeout=0.2)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError((root / "server.log").read_text())
            yield s.public_base_url, accepted["token"]
        finally:
            server.terminate()
            server.wait(timeout=10)


@pytest.mark.parametrize("width", [320, 375, 390, 768, 1024, 1440, 1920, 2560])
def test_responsive_viewer_and_all_overlaps(viewer_server, width):
    from playwright.sync_api import sync_playwright

    from tests.viewer_fixtures import TEXT

    base, token = viewer_server
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
            headless=True,
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": width, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        from tests.auth_helpers import browser_login

        browser_login(page, viewer_server[0])
        page.goto(base + "/api/jobs/" + token + "/viewer")
        page.wait_for_selector("#annotation-list button")
        assert page.locator("#annotated-text").text_content() == TEXT
        assert page.locator("#annotation-list button").count() == 7
        assert not page.locator("#annotated-text script").count()
        for identity in ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]:
            page.locator(f'[data-annotation="{identity}"]').click()
            assert identity in page.locator("#annotation-details").text_content()
            assert page.locator(".annotated.selected").count() > 0
        overlap = page.locator('[data-count="4"]').first
        assert overlap.count() > 0
        overlap.focus()
        page.keyboard.press("Enter")
        assert page.locator("#region-annotations button").count() == 4
        page.locator("#region-annotations button").nth(2).click()
        assert "synthetic-test-only" in page.locator("#annotation-details").text_content()
        assert "0.8500" in page.locator("#annotation-details").text_content()
        page.locator("#entity-search").fill("kidney")
        assert (
            page.locator("#annotation-list button").count() == 4
        )  # four mentions containing kidney
        page.locator("#entity-search").fill("")
        page.locator("#legend input").first.uncheck()
        assert page.locator("#annotation-list button").count() < 7
        page.locator("#legend input").first.check()
        page.locator("#text-search").fill("😀")
        page.locator("#find-next").click()
        page.wait_for_function("() => getSelection().toString() === '😀'")
        assert page.evaluate("getSelection().toString()") == "😀"
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        if os.environ.get("SCREENSHOT_OUTPUT") and width in (390, 1440):
            destination = Path(os.environ["SCREENSHOT_OUTPUT"])
            destination.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(destination / f"viewer-{width}.png"), full_page=True)
        page.locator("#document-search").fill("empty-predictions")
        page.wait_for_function(
            "() => document.querySelectorAll('#document-list button').length===1"
        )
        page.locator("#document-list button").click()
        page.wait_for_function(
            "() => document.querySelector('#annotated-text').textContent==='No mentions here.'"
        )
        assert not page.locator("#annotation-list button").count()
        assert page.locator("#download-link").get_attribute("href").endswith("/download/brat")
        assert not errors
        browser.close()


def test_segment_algorithm(viewer_server):
    from playwright.sync_api import sync_playwright

    base, _ = viewer_server
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
            headless=True,
            args=["--no-sandbox"],
        )
        page = browser.new_page()
        from tests.auth_helpers import browser_login

        browser_login(page, viewer_server[0])
        page.goto(base + "/annotate")
        result = page.evaluate("""async () => {
          const {segments,lanes}=await import('/ner/static/spans.js');
          const text='😀a\\r\\n漢é xyz';
          const rows=[{id:'A',start:0,end:7},{id:'B',start:1,end:5},{id:'C',start:4,end:9},{id:'D',start:4,end:9}];
          const parts=segments(text,0,rows);
          return {joined:parts.map(p=>p.text).join(''),parts,lanes:[...lanes(rows)],empty:segments(text,0,[])};
        }""")
        assert result["joined"] == "😀a\r\n漢é xyz"
        assert any(len(p["ids"]) == 4 for p in result["parts"])
        assert len({v for _, v in result["lanes"]}) == 4
        assert len(result["empty"]) == 1
        browser.close()
