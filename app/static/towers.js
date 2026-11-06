/** Read-only span towers over one copy of the source. All offsets are code points. */
import { color } from "./spans.js";
export function layoutLines(text, width, measure) {
  const lines = [];
  let line = "",
    start = 0,
    count = 0,
    lastSpace = -1;
  const glyphs =
    typeof Intl.Segmenter === "function"
      ? [
          ...new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(
            text,
          ),
        ].map((x) => x.segment)
      : Array.from(text);
  function emit(value) {
    lines.push({ text: value, start, end: start + Array.from(value).length });
    start += Array.from(value).length;
  }
  for (const glyph of glyphs) {
    if (line && measure(line + glyph) > width) {
      const points = Array.from(line);
      const cut = lastSpace > 0 ? lastSpace : points.length;
      emit(points.slice(0, cut).join(""));
      line = points.slice(cut).join("");
      lastSpace = -1;
    }
    line += glyph;
    count = Array.from(line).length;
    if (/\s/u.test(glyph)) lastSpace = count;
    if (/[\r\n]/.test(glyph)) {
      emit(line);
      line = "";
      lastSpace = -1;
    }
  }
  if (line || !lines.length) emit(line);
  return lines;
}
export function drawTowers(host, text, start, rows, onSelect, selected) {
  const width = Math.max(180, host.clientWidth - 24),
    font = "15px ui-monospace, SFMono-Regular, Consolas, monospace";
  const canvas = document.createElement("canvas"),
    ctx = canvas.getContext("2d");
  ctx.font = font;
  const measure = (s) => ctx.measureText(s.replace(/[\r\n]/g, "")).width;
  const lines = layoutLines(text, width - 16, measure),
    ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("width", "100%");
  svg.setAttribute("role", "group");
  const create = (tag, attrs, text_) => {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
    if (text_ !== undefined) n.textContent = text_;
    return n;
  };
  let y = 12;
  const labelled = new Set();
  for (const line of lines) {
    const points = Array.from(line.text),
      bounds = [0];
    if (typeof Intl.Segmenter === "function") {
      for (const glyph of new Intl.Segmenter(undefined, {
        granularity: "grapheme",
      }).segment(line.text))
        bounds.push(bounds.at(-1) + Array.from(glyph.segment).length);
    } else {
      for (let i = 1; i <= points.length; i++) bounds.push(i);
    }
    const left = start + line.start,
      right = start + line.end,
      parts = [];
    for (const a of rows) {
      if (a.start >= right || a.end <= left) continue;
      // Draw whole graphemes while retaining the exact scientific offsets in a.
      const from = bounds.findLast((x) => x <= Math.max(left, a.start) - left),
        to = bounds.find((x) => x >= Math.min(right, a.end) - left);
      const x1 = 8 + measure(points.slice(0, from).join("")),
        x2 = 8 + measure(points.slice(0, to).join(""));
      const label = !labelled.has(a.id),
        caption = `${a.label} · ${a.id}`,
        labelWidth = Math.min(
          width - 8,
          Math.max(50, measure(caption) * 0.8 + 14),
        );
      parts.push({ a, x1, x2, label, caption, labelWidth });
    }
    parts.sort(
      (a, b) => a.x1 - b.x1 || b.x2 - a.x2 || a.a.id.localeCompare(b.a.id),
    );
    const occupied = [];
    for (const p of parts) {
      p.labelX = Math.max(2, Math.min(p.x1, width - p.labelWidth - 2));
      const lo = Math.min(p.x1, p.labelX),
        hi = Math.max(p.x2, p.label ? p.labelX + p.labelWidth : p.x2);
      let lane = 0;
      while (occupied[lane]?.some(([a, b]) => lo < b + 6 && hi + 6 > a)) lane++;
      (occupied[lane] ??= []).push([lo, hi]);
      p.lane = lane;
    }
    const textY = y + occupied.length * 32 + 22;
    const brackets = create("g", { "aria-hidden": "true" });
    // Put every connector behind all tags, including tags in lower lanes.
    svg.append(brackets);
    // Only these nodes hold source text; labels and brackets are separate controls.
    const source = create(
      "text",
      {
        x: 8,
        y: textY,
        class: "tower-source",
        "data-start": left,
        "data-end": right,
        "xml:space": "preserve",
      },
      line.text.replace(/[\r\n]+$/, ""),
    );
    const ending = line.text.match(/[\r\n]+$/)?.[0];
    if (ending) source.append(create("tspan", { display: "none" }, ending));
    svg.append(source);
    for (const p of parts) {
      const top = textY - 44 - p.lane * 32;
      brackets.append(
        create("path", {
          d: `M ${p.x1} ${textY + 4} V ${top + 24} H ${Math.max(p.x1 + 1, p.x2)} V ${textY + 4}`,
          class: `tower-bracket ${color(p.a.label)}${selected === p.a.id ? " selected" : ""}`,
          "data-annotation": p.a.id,
          "data-start": p.a.start,
          "data-end": p.a.end,
          fill: "none",
        }),
      );
      // Wrapped continuations keep their brackets, with one control per entity.
      if (!p.label) continue;
      const group = create("g", {
        class: `tower-annotation ${color(p.a.label)}${selected === p.a.id ? " selected" : ""}`,
        "data-annotation": p.a.id,
        role: "button",
        tabindex: 0,
        "aria-label": `${p.a.label}: ${p.a.text} [${p.a.start}, ${p.a.end})`,
      });
      group.append(
        create(
          "title",
          {},
          `${p.a.label} · ${p.a.text}\n[${p.a.start}, ${p.a.end})\n${p.a.model_ids?.join(", ") || p.a.model_id || ""}`,
        ),
      );
      if (p.label) {
        group.append(
          create("rect", {
            x: p.labelX,
            y: top,
            width: p.labelWidth,
            height: 24,
            rx: 3,
            class: "tower-tag",
          }),
        );
        const caption = create(
          "text",
          { x: p.labelX + 6, y: top + 16, class: "tower-caption" },
          p.caption,
        );
        if (measure(p.caption) * 0.8 > p.labelWidth - 12) {
          caption.setAttribute("textLength", p.labelWidth - 12);
          caption.setAttribute("lengthAdjust", "spacingAndGlyphs");
        }
        group.append(caption);
        labelled.add(p.a.id);
      }
      const activate = () => onSelect(p.a.id);
      group.onclick = activate;
      group.onkeydown = (e) => {
        if (["Enter", " "].includes(e.key)) {
          e.preventDefault();
          activate();
        }
      };
      svg.append(group);
    }
    y = textY + 28;
  }
  svg.setAttribute("height", y);
  svg.setAttribute("viewBox", `0 0 ${width} ${y}`);
  host.replaceChildren(svg);
}
