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
export function drawTowers(
  host,
  text,
  start,
  rows,
  onSelect,
  selected,
  revealed = null,
) {
  const width = Math.max(180, host.clientWidth - 24),
    font = "15px ui-monospace, SFMono-Regular, Consolas, monospace",
    captionFont = "12px ui-monospace, SFMono-Regular, Consolas, monospace";
  const canvas = document.createElement("canvas"),
    ctx = canvas.getContext("2d");
  ctx.font = font;
  const measure = (s) => ctx.measureText(s.replace(/[\r\n]/g, "")).width;
  const measureCaption = (s) => {
    ctx.font = captionFont;
    const size = ctx.measureText(s).width;
    ctx.font = font;
    return size;
  };
  const lines = layoutLines(text, width - 16, measure),
    ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("role", "group");
  const create = (tag, attrs, text_) => {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
    if (text_ !== undefined) n.textContent = text_;
    return n;
  };
  const content = create("g", {});
  svg.append(content);
  let y = 0,
    minX = 0,
    maxX = width;
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
        labelWidth = Math.max(50, measureCaption(caption) + 16);
      parts.push({ a, x1, x2, label, caption, labelWidth });
    }
    parts.sort(
      (a, b) =>
        a.a.end - a.a.start - (b.a.end - b.a.start) ||
        a.x1 - b.x1 ||
        a.a.id.localeCompare(b.a.id),
    );
    const placed = [];
    let laneCount = 0;
    for (const p of parts) {
      p.center = (p.x1 + p.x2) / 2;
      p.labelX = p.center - p.labelWidth / 2;
      const lo = Math.min(p.x1, p.label ? p.labelX : p.x1),
        hi = Math.max(p.x2, p.label ? p.labelX + p.labelWidth : p.x2);
      // Increasing span length gives every intersecting larger span a higher row.
      p.lane = placed.reduce(
        (lane, other) =>
          lo < other.hi + 8 && hi + 8 > other.lo
            ? Math.max(lane, other.lane + 1)
            : lane,
        0,
      );
      placed.push({ lo, hi, lane: p.lane });
      laneCount = Math.max(laneCount, p.lane + 1);
      minX = Math.min(minX, lo - 4);
      maxX = Math.max(maxX, hi + 4);
    }
    const textY = y + laneCount * 40 + 28;
    const lineGroup = create("g", {
      class: "tower-line",
      "data-start": left,
      "data-end": right,
    });
    content.append(lineGroup);
    const brackets = create("g", { "aria-hidden": "true" });
    // Put every connector behind all tags, including tags in lower lanes.
    lineGroup.append(brackets);
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
    lineGroup.append(source);
    for (const p of parts) {
      const top = textY - 56 - p.lane * 40,
        railY = top + 30;
      brackets.append(
        create("path", {
          d: `M ${p.x1} ${railY + 4} V ${railY} H ${Math.max(p.x1 + 1, p.x2)} V ${railY + 4}`,
          class: `tower-bracket ${color(p.a.label)}${revealed === p.a.id ? " revealed" : ""}`,
          "data-annotation": p.a.id,
          "data-start": p.a.start,
          "data-end": p.a.end,
          "data-lane": p.lane,
          fill: "none",
        }),
      );
      // Wrapped continuations keep their brackets, with one control per entity.
      if (!p.label) continue;
      const group = create("g", {
        class: `tower-annotation ${color(p.a.label)}${selected === p.a.id ? " selected" : ""}`,
        "data-annotation": p.a.id,
        "data-start": p.a.start,
        "data-end": p.a.end,
        "data-lane": p.lane,
        role: "button",
        tabindex: 0,
        "aria-label": `${p.a.label}: ${p.a.text} [${p.a.start}, ${p.a.end})`,
        "aria-pressed": String(revealed === p.a.id),
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
            height: 26,
            rx: 3,
            class: "tower-tag",
          }),
        );
        const caption = create(
          "text",
          {
            x: p.center,
            y: top + 17,
            "text-anchor": "middle",
            class: "tower-caption",
          },
          p.caption,
        );
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
      lineGroup.append(group);
    }
    y = textY + 20;
  }
  // Keep exact centering at the line edges. Overflow scrolls instead of shifting
  // labels away from their entity or shrinking their text to fit the viewport.
  const totalWidth = maxX - minX;
  content.setAttribute("transform", `translate(${-minX} 0)`);
  svg.setAttribute("width", totalWidth);
  svg.setAttribute("height", y);
  svg.setAttribute("viewBox", `0 0 ${totalWidth} ${y}`);
  host.replaceChildren(svg);
}
