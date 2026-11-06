"""Reader text/geometry stays unchanged with dense, internal-word and Unicode overlaps."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tests.auth_helpers import browser_login

pytestmark = pytest.mark.skipif(
    os.environ.get("BROWSER_TESTS") != "1", reason="Actual Chromium opt-in"
)

WORD = "adenocarcinoma was observed."
DENSE = "Severe chronic kidney disease was reported in a synthetic document."
UNICODE = "Cafe\u0301, 漢字 and 👩\u200d🔬.\r\nSynthetic text."
CLINICAL = "Enfermedad renal crónica avanzada. Trasplante renal con rechazo agudo."
CASES = [
    ("inside-word", WORD, [("DISEASE", 0, 14), ("SYMPTOM", 0, 5), ("PROCEDURE", 5, 14)]),
    (
        "clinical-synthetic",
        CLINICAL,
        [
            ("DISEASE", 0, len("Enfermedad renal crónica avanzada")),
            ("DISEASE", CLINICAL.index("renal"), len("Enfermedad renal crónica")),
            ("TEMPORALITY", CLINICAL.index("crónica"), CLINICAL.index("crónica") + len("crónica")),
            (
                "PROCEDURE",
                CLINICAL.index("Trasplante"),
                CLINICAL.index("Trasplante") + len("Trasplante renal"),
            ),
            ("EVENT", CLINICAL.index("Trasplante"), len(CLINICAL) - 1),
            ("DISEASE", CLINICAL.index("rechazo"), len(CLINICAL) - 1),
        ],
    ),
    (
        "dense",
        DENSE,
        [("OUTER", 0, 29), ("CROSSING", 18, 40), *[(f"TYPE_{i}", 7, 29) for i in range(16)]],
    ),
    (
        "unicode",
        UNICODE,
        [
            ("FULL", 0, len(UNICODE)),
            ("CAFE", 0, 5),
            ("ACCENT", 3, 5),
            ("BASE", 3, 4),
            ("EMOJI", UNICODE.index("👩"), UNICODE.index("👩") + 3),
        ],
    ),
]


@pytest.fixture(scope="module", params=CASES, ids=[row[0] for row in CASES])
def overlap_server(tmp_path_factory, request):
    from app.config import Settings
    from tests.viewer_fixtures import seed_viewer

    name, text, ranges = request.param
    root = tmp_path_factory.mktemp("overlap-" + name)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}/ner"
    settings = Settings(
        _env_file=None,
        storage_root=root / "private",
        app_prefix="/ner",
        public_base_url=base,
        app_env="test",
        cookie_secure=False,
        mail_backend="memory",
        min_free_disk_mb=0,
    )
    _, job, _, _ = seed_viewer(settings, text=text, ranges=ranges)
    env = {
        **os.environ,
        "STORAGE_ROOT": str(settings.storage_root),
        "APP_PREFIX": "/ner",
        "PUBLIC_BASE_URL": base,
        "APP_ENV": "test",
        "COOKIE_SECURE": "false",
        "MAIL_BACKEND": "file",
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
                    urllib.request.urlopen(base + "/health", timeout=0.2)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("Controlled overlap server did not start")
            yield base, job["job_id"], name, text, ranges
        finally:
            server.terminate()
            server.wait(timeout=10)


@pytest.mark.parametrize("width", [320, 390, 1440])
def test_overlaps_do_not_insert_text_or_change_character_layout(overlap_server, width):
    from playwright.sync_api import sync_playwright

    base, job, name, text, ranges = overlap_server
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
            headless=True,
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": width, "height": 900})
        browser_login(page, base)
        page.goto(base + "/jobs/" + job + "/viewer")
        page.wait_for_function(
            '(text)=>document.querySelector("#annotated-text")?.textContent===text', arg=text
        )
        assert page.locator("#annotation-list button").count() == len(ranges)
        assert page.locator("#annotated-text").text_content() == text
        layout = page.evaluate("""() => {
          const reader=document.querySelector('#annotated-text');
          const copy=reader.cloneNode(false);copy.removeAttribute('id');copy.setAttribute('aria-hidden','true');
          copy.style.visibility='hidden';copy.style.position='absolute';copy.style.width=reader.getBoundingClientRect().width+'px';copy.textContent=reader.textContent;reader.parentElement.append(copy);
          function positions(root){
            const box=root.getBoundingClientRect(),walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),out=[];let node;
            while(node=walker.nextNode()){
              let offset=0;
              for(const point of Array.from(node.data)){
                const range=document.createRange();range.setStart(node,offset);range.setEnd(node,offset+point.length);
                const r=range.getBoundingClientRect();out.push({point,x:r.x-box.x,y:r.y-box.y});offset+=point.length;
              }
            }
            return out;
          }
          const annotated=positions(reader),plain=positions(copy);
          const pseudo=[...reader.querySelectorAll('.annotated')].map(node=>getComputedStyle(node,'::after').content);
          const range=document.createRange();range.selectNodeContents(reader);
          const result={annotated,plain,pseudo,rangeText:range.toString(),fits:reader.scrollWidth<=reader.clientWidth+1};
          copy.remove();return result;
        }""")
        assert layout["rangeText"] == text
        assert layout["fits"]
        assert all(value in ("none", "normal", '""') for value in layout["pseudo"])
        assert len(layout["annotated"]) == len(layout["plain"]) == len(text)
        # Real layout comparison catches inserted CSS counters even when textContent is correct.
        for actual, plain in zip(layout["annotated"], layout["plain"]):
            assert actual["point"] == plain["point"]
            assert abs(actual["x"] - plain["x"]) < 1, (actual, plain)
            assert abs(actual["y"] - plain["y"]) < 1, (actual, plain)
        # Every legitimate annotation is still reachable through its region, not hidden/dropped.
        for identity in page.locator("#annotation-list button").evaluate_all(
            "(nodes)=>nodes.map(n=>n.dataset.annotation)"
        ):
            region = page.locator("#annotated-text [data-ids]")
            targets = region.evaluate_all(
                '(nodes,id)=>nodes.filter(n=>n.dataset.ids.split(" ").includes(id)).map(n=>n.dataset.start)',
                identity,
            )
            assert targets
            node = page.locator(f'#annotated-text [data-start="{targets[0]}"]')
            node.focus()
            page.keyboard.press("Enter")
            assert identity in page.locator("#region-annotations").text_content()
        if os.environ.get("SCREENSHOT_OUTPUT"):
            path = Path(os.environ["SCREENSHOT_OUTPUT"])
            path.mkdir(parents=True, exist_ok=True)
            page.locator(".reading-panel").screenshot(path=str(path / f"{name}-{width}.png"))
        page.locator('[data-reader-mode="towers"]').click()
        page.wait_for_selector(".tower-caption")
        assert page.locator(".tower-caption").count() == len(ranges)
        assert page.locator(".tower-annotation").count() == len(ranges)
        assert "".join(page.locator(".tower-source").all_text_contents()) == text
        geometry_script = """() => {
          const tags=[...document.querySelectorAll('.tower-tag')].map(n=>n.getBoundingClientRect());
          const collisions=tags.flatMap((a,i)=>tags.slice(i+1).filter(b=>a.left<b.right-.1 && a.right>b.left+.1 && a.top<b.bottom-.1 && a.bottom>b.top+.1));
          const sources=[...document.querySelectorAll('.tower-source')].map(n=>n.getBoundingClientRect());
          const textCollisions=tags.some(a=>sources.some(b=>a.left<b.right && a.right>b.left && a.top<b.bottom && a.bottom>b.top));
          const errors=[...document.querySelectorAll('.tower-bracket')].map(path=>{
            const line=path.parentNode.nextElementSibling, text=line.textContent, points=Array.from(text), left=Number(line.dataset.start);
            const bounds=[0];for(const g of new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(text))bounds.push(bounds.at(-1)+Array.from(g.segment).length);
            const from=bounds.findLast(x=>x<=Math.max(left,Number(path.dataset.start))-left);
            const to=bounds.find(x=>x>=Math.min(Number(line.dataset.end),Number(path.dataset.end))-left);
            const position=n=>{const size=points.slice(0,n).join('').replace(/[\\r\\n]/g,'').length;return 8+(size?line.getSubStringLength(0,size):0);};
            const first=path.getPointAtLength(0),last=path.getPointAtLength(path.getTotalLength());
            return {start:Math.abs(first.x-position(from)),end:Math.abs(last.x-Math.max(position(from)+1,position(to)))};
          });
          const paths=[...document.querySelectorAll('.tower-bracket')];
          const lineBoxes=[...document.querySelectorAll('.tower-line')].map(n=>n.getBoundingClientRect());
          const lineCollisions=lineBoxes.some((a,i)=>lineBoxes.slice(i+1).some(b=>a.top<b.bottom && a.bottom>b.top));
          const railCollisions=paths.some(p=>{const a=p.getBoundingClientRect();return [...tags,...sources].some(b=>a.left<b.right && a.right>b.left && a.top<b.bottom && a.bottom>b.top);});
          const centers=[...document.querySelectorAll('.tower-annotation')].map(n=>{
            const tag=n.querySelector('.tower-tag').getBoundingClientRect();
            const path=[...n.parentNode.querySelectorAll('.tower-bracket')].find(p=>p.dataset.annotation===n.dataset.annotation).getBoundingClientRect();
            const caption=n.querySelector('.tower-caption');
            return {error:Math.abs(tag.x+tag.width/2-path.x-path.width/2),font:parseFloat(getComputedStyle(caption).fontSize),scale:caption.getScreenCTM().a,fits:caption.getComputedTextLength()<=tag.width-14,compressed:caption.hasAttribute('textLength')};
          });
          const orderErrors=[...document.querySelectorAll('.tower-line')].flatMap(line=>{
            const spans=[...line.querySelectorAll('.tower-bracket')];
            return spans.flatMap(a=>spans.filter(b=>Number(a.dataset.end)-Number(a.dataset.start)<Number(b.dataset.end)-Number(b.dataset.start) && Number(a.dataset.start)<Number(b.dataset.end) && Number(a.dataset.end)>Number(b.dataset.start) && a.getBoundingClientRect().y<=b.getBoundingClientRect().y));
          }).length;
          return {collisions:collisions.length,textCollisions,lineCollisions,railCollisions,errors,centers,orderErrors};
        }"""
        geometry = page.evaluate(geometry_script)
        assert geometry["collisions"] == 0
        assert not geometry["textCollisions"]
        assert not geometry["lineCollisions"]
        assert not geometry["railCollisions"]
        assert geometry["orderErrors"] == 0
        assert all(
            row["error"] < 1
            and row["font"] == 12
            and abs(row["scale"] - 1) < 0.001
            and row["fits"]
            and not row["compressed"]
            for row in geometry["centers"]
        ), geometry
        assert all(row["start"] < 1 and row["end"] < 1 for row in geometry["errors"]), geometry
        for identity in page.locator(".tower-annotation").evaluate_all(
            "(nodes)=>nodes.map(n=>n.dataset.annotation)"
        ):
            page.locator(f'.tower-annotation[data-annotation="{identity}"]').first.focus()
            page.keyboard.press("Enter")
            assert identity in page.locator("#annotation-details").text_content()
            assert page.evaluate("document.activeElement.dataset.annotation") == identity
        # Each line remains independent after reflow; fonts and labels never shrink.
        for next_width in (width + 80, width):
            old_svg = page.locator("#tower-view > svg").element_handle()
            focused = page.evaluate("document.activeElement.dataset.annotation")
            page.set_viewport_size({"width": next_width, "height": 900})
            page.wait_for_function("old=>!old.isConnected", arg=old_svg)
            resized = page.evaluate(geometry_script)
            assert not any(
                resized[key]
                for key in (
                    "lineCollisions",
                    "railCollisions",
                    "collisions",
                    "textCollisions",
                    "orderErrors",
                )
            ), resized
            assert all(
                row["error"] < 1 and row["fits"] and abs(row["scale"] - 1) < 0.001
                for row in resized["centers"]
            ), resized
            assert page.evaluate("document.activeElement.dataset.annotation") == focused
        if name == "inside-word" and width == 390:
            page.locator('.tower-annotation[data-annotation="T3"]').focus()
            page.keyboard.press("Space")
            contracts = page.evaluate("""async () => {
              const {color,ENTITY_COLORS}=await import(document.querySelector('script[src$="viewer.js"]').src.replace('viewer.js','spans.js'));
              const {layoutLines}=await import(document.querySelector('script[src$="viewer.js"]').src.replace('viewer.js','towers.js'));
              const samples=['a  b\\r\\n\\nCafe\\u0301 👩‍🔬漢字','a'.repeat(100),'','last character.'];
              return {categories:Object.keys(ENTITY_COLORS), colors:Object.values(ENTITY_COLORS), same:color('DISEASE')===color('ENFERMEDAD')&&color('disease')===color('MALALTIA')&&color('MEDICATION')===color('DRUG'), unknown:color('NEW_LABEL'),
                roundtrips:samples.every(s=>[1,4,12].every(w=>{
                  const lines=layoutLines(s,w,x=>Array.from(x).length);
                  return lines.map(l=>l.text).join('')===s&&lines.every((l,i)=>l.end-l.start===Array.from(l.text).length&&l.start===(i?lines[i-1].end:0));
                }))};
            }""")
            assert len(set(contracts["colors"])) == 13
            import yaml

            catalog = yaml.safe_load(Path("catalog/models.yaml").read_text())
            categories = {
                key for language in catalog["languages"].values() for key in language["entities"]
            }
            assert set(contracts["categories"]) == categories
            assert contracts["same"] and contracts["roundtrips"]
            assert contracts["unknown"] == "entity-other"
            assert page.locator("#annotation-details blockquote").text_content() == "carcinoma"
        if os.environ.get("AXE_CORE_PATH"):
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
                    output.write(
                        json.dumps(
                            {
                                "screen": "Entity towers / " + name,
                                "viewport": page.viewport_size,
                                "axe_version": result["testEngine"]["version"],
                                "violations": [],
                                "incomplete_rules": [row["id"] for row in result["incomplete"]],
                            }
                        )
                        + "\n"
                    )
        if os.environ.get("SCREENSHOT_OUTPUT"):
            page.locator(".reading-panel").screenshot(path=str(path / f"towers-{name}-{width}.png"))
        page.locator('[data-reader-mode="inline"]').click()
        page.select_option("#auth-locale", "es")
        assert page.locator("#annotated-text").text_content() == text
        assert "Anotaciones solapadas:" in page.locator("#overlap-summary").text_content()
        browser.close()
