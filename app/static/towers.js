/** Read-only span towers over one copy of the source. All offsets are code points. */
import { color, lanes, segments } from "./spans.js";
/** Minimal interval coloring per overlap component; touching spans share a lane. */
export function overlapLanes(rows) {
  const result = new Map();
  const sorted = [...rows].sort(
    (a, b) => a.start - b.start || b.end - a.end || a.id.localeCompare(b.id),
  );
  let component = [],
    end = -Infinity;
  function flush() {
    if (!component.length) return;
    const colors = lanes(component),
      sizes = new Map();
    for (const row of component) {
      const lane = colors.get(row.id);
      sizes.set(lane, Math.max(sizes.get(lane) || 0, row.end - row.start));
    }
    // Prefer short mentions near the source without increasing overlap depth.
    const ordered = [...sizes.keys()].sort(
      (a, b) => sizes.get(a) - sizes.get(b) || b - a,
    );
    for (const row of component)
      result.set(row.id, ordered.indexOf(colors.get(row.id)));
    component = [];
  }
  for (const row of sorted) {
    if (row.start >= end) {
      flush();
      end = -Infinity;
    }
    component.push(row);
    end = Math.max(end, row.end);
  }
  flush();
  return result;
}
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
  const scroll = { left: host.scrollLeft, top: host.scrollTop };
  const scale =
    parseFloat(getComputedStyle(document.documentElement).fontSize) / 16;
  const width = Math.max(180, (host.clientWidth - 24) / scale),
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
  host.replaceChildren(svg);
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
      const label = !labelled.has(a.id),
        caption = `${a.label} · ${a.id}`,
        labelWidth = Math.max(50, measureCaption(caption) + 16);
      parts.push({ a, from, to, label, caption, labelWidth });
    }
    const lineGroup = create("g", {
      class: "tower-line",
      "data-start": left,
      "data-end": right,
    });
    content.append(lineGroup);
    const coverage = create("g", {
      class: "tower-coverage",
      "aria-hidden": "true",
    });
    lineGroup.append(coverage);
    const brackets = create("g", { "aria-hidden": "true" });
    lineGroup.append(brackets);
    const source = create("text", {
      x: 8,
      y: 0,
      class: "tower-source",
      "data-start": left,
      "data-end": right,
      "xml:space": "preserve",
    });
    lineGroup.append(source);
    const gaps = new Map(),
      visible = line.text.replace(/[\r\n]+$/, ""),
      ending = line.text.slice(visible.length),
      glyphs = Array.from(visible);
    function sourceSpacing() {
      source.replaceChildren();
      const cuts = [
        0,
        ...[...gaps.keys()]
          .filter((n) => n > 0 && n < glyphs.length)
          .sort((a, b) => a - b),
        glyphs.length,
      ];
      for (let i = 0; i < cuts.length - 1; i++) {
        const value = glyphs.slice(cuts[i], cuts[i + 1]).join("");
        source.append(
          gaps.has(cuts[i])
            ? create("tspan", { dx: gaps.get(cuts[i]) }, value)
            : document.createTextNode(value),
        );
      }
      if (ending) source.append(create("tspan", { display: "none" }, ending));
      for (const p of parts) {
        p.x1 = position(p.from, false);
        p.x2 = position(p.to, true);
        p.center = (p.x1 + p.x2) / 2;
        p.labelX = p.center - p.labelWidth / 2;
      }
    }
    function position(offset, last) {
      const count = source.getNumberOfChars();
      const n = points
        .slice(0, offset)
        .join("")
        .replace(/[\r\n]/g, "").length;
      if (!count || (last && !n)) return 8;
      if (last || n >= count)
        return source.getEndPositionOfChar(Math.min(n, count) - 1).x;
      return source.getStartPositionOfChar(n).x;
    }
    const assignments = overlapLanes(parts.map((p) => p.a));
    for (const p of parts) p.lane = assignments.get(p.a.id);
    const laneCount = parts.reduce(
      (count, p) => Math.max(count, p.lane + 1),
      0,
    );
    sourceSpacing();
    // Caption width never creates vertical levels. Make room horizontally between
    // disjoint mentions with SVG offsets, keeping source text and labels intact.
    for (let lane = 0; lane < laneCount; lane++) {
      const tags = parts
        .filter((p) => p.label && p.lane === lane)
        .sort((a, b) => a.a.start - b.a.start);
      for (let i = 1; i < tags.length; i++) {
        const before = tags[i - 1],
          after = tags[i];
        const deficit = before.labelX + before.labelWidth + 8 - after.labelX;
        if (
          deficit > 0 &&
          after.from >= before.to &&
          after.from < glyphs.length
        ) {
          gaps.set(after.from, (gaps.get(after.from) || 0) + deficit);
          sourceSpacing();
        }
      }
    }
    for (const p of parts) {
      minX = Math.min(minX, p.x1 - 4, p.label ? p.labelX - 4 : p.x1);
      maxX = Math.max(
        maxX,
        p.x2 + 4,
        p.label ? p.labelX + p.labelWidth + 4 : p.x2,
      );
    }
    maxX = Math.max(maxX, source.getBBox().x + source.getBBox().width + 8);
    const ascent = Math.max(0, -source.getBBox().y),
      bandGap = parts.length ? Math.max(0, ascent - 10) : 0,
      textY = y + laneCount * 40 + 28 + bandGap;
    source.setAttribute("y", textY);
    const byId = new Map(parts.map((p) => [p.a.id, p.a]));
    // Partition the visible source at annotation boundaries. Each intersection
    // shares one fixed-height band between its category colors, without hiding
    // a category behind another or adding copies of the original text.
    for (const segment of segments(
      visible,
      0,
      parts.map((p) => ({
        id: p.a.id,
        start: p.from,
        end: p.to,
      })),
    )) {
      if (!segment.ids.length) continue;
      const colors = [
        ...new Set(segment.ids.map((id) => color(byId.get(id).label))),
      ].sort();
      const band = create("g", {
        class: "tower-coverage-segment",
        "data-start": left + segment.start,
        "data-end": left + segment.end,
        "data-annotations": segment.ids.join(" "),
      });
      const x = position(segment.start, false),
        width = Math.max(1, position(segment.end, true) - x);
      colors.forEach((category, index) =>
        band.append(
          create("rect", {
            class: `tower-coverage-band ${category}`,
            x,
            y: textY - ascent - 8 + (index * 6) / colors.length,
            width,
            height: 6 / colors.length,
          }),
        ),
      );
      coverage.append(band);
    }
    for (const p of parts) {
      const top = textY - bandGap - 56 - p.lane * 40,
        railY = top + 30;
      brackets.append(
        create("path", {
          d: `M ${p.x1} ${railY + 4} V ${railY} H ${Math.max(p.x1 + 1, p.x2)} V ${railY + 4}`,
          class: `tower-bracket ${color(p.a.label)}${selected === p.a.id ? " selected" : ""}`,
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
        "aria-pressed": String(selected === p.a.id),
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
  svg.setAttribute("width", totalWidth * scale);
  svg.setAttribute("height", y * scale);
  svg.setAttribute("viewBox", `0 0 ${totalWidth} ${y}`);
  host.scrollLeft = scroll.left;
  host.scrollTop = scroll.top;
}
