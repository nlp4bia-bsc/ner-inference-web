"""Isolate the actual sweep-line algorithm and safe DOM fragment cost on synthetic spans."""

import json
import os
import platform
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    source = Path("app/static/spans.js").read_text()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_EXECUTABLE", "/usr/bin/chromium"),
            headless=True,
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        # about:blank has no product data/CSP; the production application retains strict CSP.
        results = page.evaluate(
            """source => {
          const {segments,lanes}=new Function(source.replaceAll('export ', '')+';return {segments,lanes};')();
          return [100,1000,3000].map(count=>{
            const text='😀'+('a '.repeat(2499))+'é';
            const rows=Array.from({length:count},(_,i)=>({id:'T'+i,start:(i*7)%4800,end:Math.min(5000,(i*7)%4800+50+i%500)}));
            const start=performance.now(),parts=segments(text,0,rows),levels=lanes(rows),segmented=performance.now();
            const fragment=document.createDocumentFragment();for(const part of parts){const span=document.createElement('span');span.textContent=part.text;span.dataset.count=part.ids.length;fragment.append(span);}document.body.replaceChildren(fragment);void document.body.offsetHeight;
            return {annotations:count,atomic_segments:parts.length,lanes:Math.max(...levels.values())+1,segmentation_ms:segmented-start,plain_dom_layout_ms:performance.now()-segmented};
          });
        }""",
            source,
        )
        browser.close()
    payload = {
        "platform": platform.platform(),
        "viewport": "1440x900",
        "note": "Actual segments/lanes module with synthetic spans; plain DOM layout excludes product CSS, HTTP and neural inference. Functional app rendering is covered separately.",
        "cases": results,
    }
    Path("work/benchmark-viewer.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
