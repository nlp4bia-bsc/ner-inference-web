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
DISJOINT_CLINICAL = "Artralgias, tos irritativa, afonía, cefalea, astenia y náuseas.\nTratada con amoxicilina y paracetamol."
CASES = [
    (
        "clinical-disjoint",
        DISJOINT_CLINICAL,
        [
            (label, DISJOINT_CLINICAL.index(term), DISJOINT_CLINICAL.index(term) + len(term))
            for label, term in [
                *[
                    ("SYMPTOM", term)
                    for term in (
                        "Artralgias",
                        "tos irritativa",
                        "afonía",
                        "cefalea",
                        "astenia",
                        "náuseas",
                    )
                ],
                ("MEDICATION", "amoxicilina"),
                ("MEDICATION", "paracetamol"),
            ]
        ],
    ),
    ("separate-short", "a b c", [("DISEASE", 0, 1), ("SYMPTOM", 2, 3), ("PROCEDURE", 4, 5)]),
    (
        "pair-plus-separated",
        "abcdef g h",
        [("DISEASE", 0, 6), ("SYMPTOM", 1, 4), ("MEDICATION", 7, 8), ("PROCEDURE", 9, 10)],
    ),
    (
        "triple-plus-separated",
        "abcdef g h",
        [
            ("DISEASE", 0, 6),
            ("SYMPTOM", 1, 5),
            ("PROCEDURE", 2, 4),
            ("MEDICATION", 7, 8),
            ("PROCEDURE", 9, 10),
        ],
    ),
    (
        "crossing-chain",
        "abcdefghij k",
        [("DISEASE", 0, 3), ("SYMPTOM", 2, 6), ("PROCEDURE", 5, 10), ("MEDICATION", 11, 12)],
    ),
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
        model_loading_mode="validated_local",
        require_email_verification=True,
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


@pytest.mark.parametrize("width", [320, 390, 1440, 3840])
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
        visible_lines_script = """() => [...new Set([...document.querySelectorAll('.tower-bracket')]
          .filter(n=>Number(getComputedStyle(n).opacity)>0).flatMap(n=>JSON.parse(n.dataset.spans).map(s=>s.id)))].sort()"""
        # Every annotation has a colored bracket before any tower is activated.
        expected_visible = sorted(
            page.locator(".tower-annotation").evaluate_all(
                "nodes=>nodes.map(n=>n.dataset.annotation)"
            )
        )
        assert page.evaluate(visible_lines_script) == expected_visible
        assert page.locator(".tower-caption").count() == len(ranges)
        assert page.locator("#tower-view rect").count() == len(ranges)
        # Every tower keeps its category color before selection, including custom labels.
        # Query and measure in one evaluation: ResizeObserver can replace the SVG.
        colors = page.evaluate("""() => [...document.querySelectorAll('.tower-annotation')].map(node => {
          const style = getComputedStyle(node), tag = node.querySelector('.tower-tag');
          const probe = document.createElementNS('http://www.w3.org/2000/svg','rect');
          probe.style.fill = style.getPropertyValue('--entity-color'); node.append(probe);
          const expected = getComputedStyle(probe).fill;
          probe.style.fill = style.getPropertyValue('--entity-text').trim() || '#ffffff';
          const expectedCaption = getComputedStyle(probe).fill; probe.remove();
          return {fill:getComputedStyle(tag).fill, expected,
            caption:getComputedStyle(node.querySelector('.tower-caption')).fill,expectedCaption};
        })""")
        assert all(
            row["fill"] == row["expected"] and row["caption"] == row["expectedCaption"]
            for row in colors
        ), colors
        assert page.locator(".tower-coverage-band, .tower-coverage-segment").count() == 0
        if name == "pair-plus-separated":
            shared = page.evaluate("""() => [...document.querySelectorAll('.tower-bracket')].map(path=>{
              const gradient=document.getElementById(path.getAttribute('stroke').match(/#([^)]*)/)[1]);
              return {start:Number(path.dataset.start),end:Number(path.dataset.end),
                ids:JSON.parse(path.dataset.spans).map(s=>s.id).sort(),
                colors:[...new Set([...gradient.children].map(n=>getComputedStyle(n).stopColor))].sort()};
            })""")
            assert shared == [
                {
                    "start": 0,
                    "end": 6,
                    "ids": ["T1", "T2"],
                    "colors": ["rgb(239, 141, 28)", "rgb(240, 166, 198)"],
                },
                {"start": 7, "end": 8, "ids": ["T3"], "colors": ["rgb(8, 125, 63)"]},
                {"start": 9, "end": 10, "ids": ["T4"], "colors": ["rgb(21, 91, 197)"]},
            ]
            overlap_colors = page.evaluate("""() => {
              const path=document.querySelector('.tower-bracket[data-start="0"]'),source=path.closest('.tower-line').querySelector('.tower-source');
              const gradient=document.getElementById(path.getAttribute('stroke').match(/#([^)]*)/)[1]),x1=Number(gradient.getAttribute('x1')),width=Number(gradient.getAttribute('x2'))-x1;
              const low=(source.getStartPositionOfChar(1).x-x1)/width,high=(source.getEndPositionOfChar(3).x-x1)/width;
              const orange=[...gradient.children].filter(n=>getComputedStyle(n).stopColor==='rgb(239, 141, 28)'),tolerance=.25/width;
              // Final SVG scaling can round glyph positions by a fraction of a pixel.
              return {count:orange.length,low,high,width,offsets:orange.map(n=>Number(n.getAttribute('offset'))),outside:orange.filter(n=>Number(n.getAttribute('offset'))<low-tolerance||Number(n.getAttribute('offset'))>high+tolerance).length};
            }""")
            assert overlap_colors["count"] > 0 and overlap_colors["outside"] == 0, overlap_colors
        assert page.locator(".tower-annotation").count() == len(ranges)
        assert "".join(page.locator(".tower-source").all_text_contents()) == text
        region_errors = page.evaluate(
            """ranges => [...document.querySelectorAll('.tower-line')].flatMap(line=>{
          const source=line.querySelector('.tower-source'),text=source.textContent.replace(/[\\r\\n]+$/,''),left=Number(line.dataset.start),right=left+Array.from(text).length;
          const bounds=[0];for(const g of new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(text))bounds.push(bounds.at(-1)+Array.from(g.segment).length);
          const spans=ranges.map(([label,start,end],i)=>({id:'T'+(i+1),start,end})).filter(s=>s.start<right&&s.end>left)
            .map(s=>({...s,start:left+bounds.findLast(b=>b<=Math.max(left,s.start)-left),end:left+bounds.find(b=>b>=Math.min(right,s.end)-left)})).sort((a,b)=>a.start-b.start||a.end-b.end);
          const expected=[];for(const s of spans){const r=expected.at(-1);if(r&&s.start<r.end){r.end=Math.max(r.end,s.end);r.ids.push(s.id);}else expected.push({start:s.start,end:s.end,ids:[s.id]});}
          for(const r of expected)r.ids.sort();
          const actual=[...line.querySelectorAll('.tower-bracket')].map(p=>({start:Number(p.dataset.start),end:Number(p.dataset.end),ids:JSON.parse(p.dataset.spans).map(s=>s.id).sort()}));
          return JSON.stringify(actual)===JSON.stringify(expected)?[]:[{expected,actual}];
        })""",
            ranges,
        )
        assert not region_errors, region_errors
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
            const position=(n,last=false)=>{const size=points.slice(0,n).join('').replace(/[\\r\\n]/g,'').length,count=line.getNumberOfChars();if(!count||(last&&!size))return 8;if(last||size>=count)return line.getEndPositionOfChar(Math.min(size,count)-1).x;return line.getStartPositionOfChar(size).x;};
            const first=path.getPointAtLength(0),last=path.getPointAtLength(path.getTotalLength());
            return {start:Math.abs(first.x-position(from)),end:Math.abs(last.x-Math.max(position(from)+1,position(to,true)))};
          });
          const paths=[...document.querySelectorAll('.tower-bracket')];
          const bracketGaps=paths.map(path=>{
            const source=path.parentNode.nextElementSibling;
            return (source.getBoundingClientRect().top-path.getBoundingClientRect().bottom)/source.getScreenCTM().a;
          });
          const lineBoxes=[...document.querySelectorAll('.tower-line')].map(n=>n.getBoundingClientRect());
          const lineCollisions=lineBoxes.some((a,i)=>lineBoxes.slice(i+1).some(b=>a.top<b.bottom && a.bottom>b.top));
          const railCollisions=paths.some(p=>{const a=p.getBoundingClientRect();return [...tags,...sources].some(b=>a.left<b.right && a.right>b.left && a.top<b.bottom && a.bottom>b.top);});
          const centers=[...document.querySelectorAll('.tower-annotation')].map(n=>{
            const tag=n.querySelector('.tower-tag').getBoundingClientRect();
            const source=n.parentNode.querySelector('.tower-source'), points=Array.from(source.textContent),left=Number(source.dataset.start);
            const bounds=[0];for(const g of new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(source.textContent))bounds.push(bounds.at(-1)+Array.from(g.segment).length);
            const from=bounds.findLast(x=>x<=Math.max(left,Number(n.dataset.start))-left),to=bounds.find(x=>x>=Math.min(Number(source.dataset.end),Number(n.dataset.end))-left);
            const position=(offset,last=false)=>{const count=source.getNumberOfChars(),i=points.slice(0,offset).join('').replace(/[\\r\\n]/g,'').length;if(!count||(last&&!i))return 8;if(last||i>=count)return source.getEndPositionOfChar(Math.min(i,count)-1).x;return source.getStartPositionOfChar(i).x;};
            const center=new DOMPoint((position(from)+position(to,true))/2,0).matrixTransform(source.getScreenCTM());
            const caption=n.querySelector('.tower-caption');
            return {error:Math.abs(tag.x+tag.width/2-center.x),font:parseFloat(getComputedStyle(caption).fontSize),scale:caption.getScreenCTM().a,fits:caption.getComputedTextLength()<=tag.width-14,compressed:caption.hasAttribute('textLength')};
          });
          const orderErrors=[...document.querySelectorAll('.tower-line')].flatMap(line=>{
            const spans=[...line.querySelectorAll('.tower-annotation')];
            return spans.flatMap(a=>spans.filter(b=>Number(a.dataset.end)-Number(a.dataset.start)<Number(b.dataset.end)-Number(b.dataset.start) && Number(b.dataset.start)<=Number(a.dataset.start) && Number(b.dataset.end)>=Number(a.dataset.end) && a.getBoundingClientRect().y<=b.getBoundingClientRect().y));
          }).length;
          return {collisions:collisions.length,textCollisions,lineCollisions,railCollisions,bracketGaps,errors,centers,orderErrors};
        }"""
        geometry = page.evaluate(geometry_script)
        depth_errors = page.evaluate("""() => [...document.querySelectorAll('.tower-line')].flatMap(line=>{
          const paths=[...line.querySelectorAll('.tower-bracket')];
          if(!paths.length)return [];
          const spans=paths.flatMap(p=>JSON.parse(p.dataset.spans)).map(p=>({start:Math.max(Number(line.dataset.start),p.start),end:Math.min(Number(line.dataset.end),p.end),lane:p.lane}));
          const events=spans.flatMap(p=>[[p.start,1],[p.end,-1]]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
          let active=0,peak=0;for(const [offset,delta] of events){active+=delta;peak=Math.max(peak,active);}
          const lanes=Math.max(...spans.map(p=>p.lane))+1;
          const conflicts=spans.some((a,i)=>spans.slice(i+1).some(b=>a.start<b.end&&a.end>b.start&&a.lane===b.lane));
          return lanes===peak&&!conflicts?[]:[{lanes,peak,conflicts}];
        })""")
        assert not depth_errors, depth_errors
        assert geometry["collisions"] == 0
        assert not geometry["textCollisions"]
        assert not geometry["lineCollisions"]
        assert not geometry["railCollisions"]
        assert all(2 < gap < 4 for gap in geometry["bracketGaps"]), geometry
        assert geometry["orderErrors"] == 0
        assert all(
            row["error"] < 1
            and row["font"] == 12
            and abs(row["scale"] - (1.5 if width >= 3840 else 1.125 if width >= 1440 else 1))
            < 0.001
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
            assert page.evaluate(visible_lines_script) == expected_visible
            assert (
                page.locator(f'.tower-annotation[data-annotation="{identity}"]').get_attribute(
                    "aria-pressed"
                )
                == "true"
            )
        active_tag = page.locator(f'.tower-annotation[data-annotation="{identity}"]')
        active_tag.click()
        assert page.evaluate(visible_lines_script) == expected_visible
        active_tag.click()
        assert page.evaluate(visible_lines_script) == expected_visible
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
                row["error"] < 1
                and row["fits"]
                and abs(row["scale"] - (1.5 if width >= 3840 else 1.125 if width >= 1440 else 1))
                < 0.001
                for row in resized["centers"]
            ), resized
            assert page.evaluate("document.activeElement.dataset.annotation") == focused
            assert page.evaluate(visible_lines_script) == expected_visible
        if name == "clinical-disjoint" and width == 1440:
            previous_scroll = page.evaluate("""() => {
              const host=document.querySelector('#tower-view');
              host.scrollLeft=(host.scrollWidth-host.clientWidth)/2;
              const box=host.getBoundingClientRect();
              [...host.querySelectorAll('.tower-annotation')].find(node=>{
                const tag=node.getBoundingClientRect();return tag.left>=box.left&&tag.right<=box.right;
              }).focus({preventScroll:true});
              return host.scrollLeft;
            }""")
            page.keyboard.press("Enter")
            assert (
                abs(page.locator("#tower-view").evaluate("node=>node.scrollLeft") - previous_scroll)
                < 1
            )
        if name == "inside-word" and width == 390:
            page.locator('.tower-annotation[data-annotation="T3"]').focus()
            page.keyboard.press("Space")
            contracts = page.evaluate("""async () => {
              const {color,ENTITY_COLORS}=await import(document.querySelector('script[src$="viewer.js"]').src.replace('viewer.js','spans.js'));
              const {layoutLines,overlapLanes}=await import(document.querySelector('script[src$="viewer.js"]').src.replace('viewer.js','towers.js'));
              const samples=['a  b\\r\\n\\nCafe\\u0301 👩‍🔬漢字','a'.repeat(100),'','last character.'];
              let seed=7123;
              const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
              const minimalDepth=Array.from({length:100},()=>{
                const rows=Array.from({length:30},(_,i)=>{const start=Math.floor(random()*100);return {id:String(i),start,end:start+1+Math.floor(random()*20)};});
                const assigned=overlapLanes(rows);
                const events=rows.flatMap(r=>[[r.start,1],[r.end,-1]]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
                let active=0,peak=0;for(const [offset,delta] of events){active+=delta;peak=Math.max(peak,active);}
                return Math.max(...assigned.values())+1===peak && rows.every((a,i)=>rows.slice(i+1).every(b=>a.start>=b.end||a.end<=b.start||assigned.get(a.id)!==assigned.get(b.id)));
              }).every(Boolean);
              return {minimalDepth, categories:Object.keys(ENTITY_COLORS), colors:Object.values(ENTITY_COLORS), same:color('DISEASE')===color('ENFERMEDAD')&&color('disease')===color('MALALTIA')&&color('MEDICATION')===color('DRUG'), unknown:color('NEW_LABEL'),
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
            assert contracts["same"] and contracts["roundtrips"] and contracts["minimalDepth"]
            assert contracts["unknown"].startswith("entity-custom-")
            raw_labels = {}
            for model in catalog["models"].values():
                for raw, category in model.get("label_mapping", {}).items():
                    raw_labels.setdefault(raw, set()).add(category)
            actual_colors = page.evaluate(
                """async (labels) => {
              const {color,CUSTOM_COLOR_COUNT}=await import(document.querySelector('script[src$="viewer.js"]').src.replace('viewer.js','spans.js'));
              function styled(label) {
                const node=document.createElement('span');node.className=color(label);document.body.append(node);
                const style=getComputedStyle(node),value={color:color(label),border:style.getPropertyValue('--entity-color').trim(),background:style.getPropertyValue('--entity-bg').trim()};node.remove();return value;
              }
              return {originals:labels.map(row=>({...styled(row.raw),allowed:row.targets.map(color),bio:color('B-'+row.raw)})),
                custom:Array.from({length:CUSTOM_COLOR_COUNT},(_,i)=>{const node=document.createElement('span');node.className='entity-custom-'+i;document.body.append(node);const value=getComputedStyle(node).getPropertyValue('--entity-color').trim();node.remove();return value;}),
                extensions:Array.from({length:16},(_,i)=>styled('TYPE_'+i)),
                stable:color('NÉW_LABEL')===color('new_label')&&color('NEW_LABEL')===color('I-NEW_LABEL'),
                profession:color('PROFESIÓN')===color('PROFESSION'),drug:color('FÁRMACO')===color('MEDICATION')};
            }""",
                [{"raw": raw, "targets": sorted(targets)} for raw, targets in raw_labels.items()],
            )
            assert len(raw_labels) == 54
            assert all(
                row["color"] in row["allowed"]
                and row["bio"] == row["color"]
                and row["border"]
                and row["background"]
                for row in actual_colors["originals"]
            )
            assert len(set(actual_colors["custom"])) == 24 and all(actual_colors["custom"])
            assert all(
                row["border"] and row["background"] and row["color"].startswith("entity-custom-")
                for row in actual_colors["extensions"]
            )
            assert len({row["color"] for row in actual_colors["extensions"]}) >= 8
            assert actual_colors["stable"] and actual_colors["profession"] and actual_colors["drug"]
            assert page.locator("#annotation-details blockquote").text_content() == "carcinoma"
        if os.environ.get("AXE_CORE_PATH"):
            page.evaluate(Path(os.environ["AXE_CORE_PATH"]).read_text())
            result = page.evaluate("""async () => await axe.run(document, {
              runOnly: {type:'tag', values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}
            })""")
            assert not result["violations"], [
                {
                    "rule": row["id"],
                    "nodes": [
                        {
                            "target": node["target"],
                            "html": node["html"],
                            "summary": node["failureSummary"],
                        }
                        for node in row["nodes"]
                    ],
                }
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
        page.locator('[data-reader-mode="towers"]').click()
        assert page.evaluate(visible_lines_script) == expected_visible
        page.locator('[data-reader-mode="inline"]').click()
        page.select_option("#auth-locale", "es")
        assert page.locator("#annotated-text").text_content() == text
        if any(a[1] < b[2] and a[2] > b[1] for i, a in enumerate(ranges) for b in ranges[i + 1 :]):
            assert "Anotaciones solapadas:" in page.locator("#overlap-summary").text_content()
        else:
            assert page.locator("#overlap-summary").is_hidden()
        browser.close()
