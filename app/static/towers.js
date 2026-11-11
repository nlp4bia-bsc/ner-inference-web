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
/** A shared bracket joins overlapping spans, keeping merely adjacent spans separate. */
function bracketRegions(text, parts) {
  const regions = [];
  let current = null;
  for (const part of segments(
    text,
    0,
    parts.map((p) => ({
      id: p.a.id,
      start: p.from,
      end: p.to,
    })),
  )) {
    if (!part.ids.length) {
      current = null;
      continue;
    }
    if (
      !current ||
      !current.segments.at(-1).ids.some((id) => part.ids.includes(id))
    ) {
      current = { start: part.start, end: part.end, segments: [] };
      regions.push(current);
    }
    current.end = part.end;
    current.segments.push(part);
  }
  return regions;
}
export function drawTowers(host, text, start, rows, onSelect, selected) {
  const scroll = { left: host.scrollLeft, top: host.scrollTop };
  const scale =
    parseFloat(getComputedStyle(document.documentElement).fontSize) / 16;
  const style = getComputedStyle(host),
    pixels = Math.max(
      1,
      Math.floor(
        host.clientWidth -
          parseFloat(style.paddingLeft) -
          parseFloat(style.paddingRight),
      ),
    ),
    width = pixels / scale,
    gutter = 8,
    available = Math.max(1, width - gutter * 2);
  const font = "15px ui-monospace, SFMono-Regular, Consolas, monospace",
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
  const captions = new Map();
  function captionLayout(caption) {
    if (!captions.has(caption)) {
      const lines = layoutLines(
        caption,
        Math.max(1, available - 24),
        measureCaption,
      ).map((line) => line.text);
      captions.set(caption, {
        lines,
        width: Math.max(
          Math.min(50, available - 8),
          ...lines.map((line) => measureCaption(line) + 16),
        ),
        height: 26 + (lines.length - 1) * 14,
      });
    }
    return captions.get(caption);
  }
  const lines = layoutLines(text, available, measure),
    ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("role", "group");
  const create = (tag, attrs, text_) => {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
    if (text_ !== undefined) n.textContent = text_;
    return n;
  };
  const defs = create("defs", {}),
    content = create("g", {});
  svg.append(defs, content);
  host.replaceChildren(svg);
  let y = 0;
  const labelled = new Set();
  function prepareLine(line) {
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
        layout = captionLayout(caption);
      parts.push({
        a,
        from,
        to,
        label,
        caption,
        labelWidth: layout.width,
        labelHeight: layout.height,
        captionLines: layout.lines,
      });
    }
    const lineGroup = create("g", {
      class: "tower-line",
      "data-start": left,
      "data-end": right,
    });
    content.append(lineGroup);
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
    const sourceBox = source.getBBox();
    let minX = sourceBox.x,
      maxX = sourceBox.x + sourceBox.width + 8;
    for (const p of parts) {
      minX = Math.min(minX, p.x1 - 4, p.label ? p.labelX - 4 : p.x1);
      maxX = Math.max(
        maxX,
        p.x2 + 4,
        p.label ? p.labelX + p.labelWidth + 4 : p.x2,
      );
    }
    return {
      lineGroup,
      source,
      parts,
      bounds,
      left,
      right,
      visible,
      position,
      laneCount,
      brackets,
      minX,
      extent: maxX - minX,
    };
  }
  function splitLine(line, bounds) {
    const points = Array.from(line.text);
    let low = 1,
      high = bounds.length - 2,
      best = 1;
    // Fit against the actual SVG geometry after spacing, not just font advances.
    while (low <= high) {
      const middle = (low + high) >>> 1;
      const trial = prepareLine({
        text: points.slice(0, bounds[middle]).join(""),
        start: line.start,
        end: line.start + bounds[middle],
      });
      const fits = trial.extent <= available;
      trial.lineGroup.remove();
      if (fits) {
        best = middle;
        low = middle + 1;
      } else high = middle - 1;
    }
    let cut = bounds[best];
    // Prefer a word boundary, retaining every original space/code point.
    const whitespace = bounds
      .filter((n) => n > 0 && n <= cut && /\s/u.test(points[n - 1]))
      .at(-1);
    if (whitespace) {
      const trial = prepareLine({
        text: points.slice(0, whitespace).join(""),
        start: line.start,
        end: line.start + whitespace,
      });
      if (trial.extent <= available) cut = whitespace;
      trial.lineGroup.remove();
    }
    return [
      {
        text: points.slice(0, cut).join(""),
        start: line.start,
        end: line.start + cut,
      },
      {
        text: points.slice(cut).join(""),
        start: line.start + cut,
        end: line.end,
      },
    ];
  }
  for (let index = 0; index < lines.length; index++) {
    let line = lines[index],
      prepared = prepareLine(line);
    if (prepared.extent > available && prepared.bounds.length > 2) {
      const bounds = prepared.bounds;
      prepared.lineGroup.remove();
      const [first, rest] = splitLine(line, bounds);
      // Reflow the remainder with the next natural line rather than leaving a
      // short orphan line at the old, text-only wrap boundary.
      const next = lines[index + 1];
      if (next && !/[\r\n]$/.test(line.text) && rest.end === next.start) {
        lines.splice(index, 2, first, {
          text: rest.text + next.text,
          start: rest.start,
          end: next.end,
        });
      } else lines.splice(index, 1, first, rest);
      line = first;
      prepared = prepareLine(line);
    }
    const {
      lineGroup,
      source,
      parts,
      left,
      right,
      visible,
      position,
      laneCount,
      brackets,
      minX,
    } = prepared;
    lineGroup.setAttribute("transform", `translate(${gutter - minX} 0)`);
    const laneHeights = Array.from(
      { length: laneCount },
      (_, lane) =>
        Math.max(
          26,
          ...parts
            .filter((p) => p.label && p.lane === lane)
            .map((p) => p.labelHeight),
        ) + 14,
    );
    const laneOffset = (lane) =>
      laneHeights.slice(0, lane).reduce((sum, height) => sum + height, 0);
    const ascent = Math.max(0, -source.getBBox().y),
      bracketGap = parts.length ? Math.max(0, ascent - 16) : 0,
      textY = y + laneOffset(laneCount) + 28 + bracketGap;
    source.setAttribute("y", textY);
    const byId = new Map(parts.map((p) => [p.a.id, p])),
      railY = textY - ascent - 7;
    bracketRegions(visible, parts).forEach((region, index) => {
      const ids = [
          ...new Set(region.segments.flatMap((segment) => segment.ids)),
        ],
        x1 = position(region.start, false),
        x2 = Math.max(x1 + 1, position(region.end, true)),
        gradientId = `tower-bracket-${line.start}-${index}`,
        gradient = create("linearGradient", {
          id: gradientId,
          gradientUnits: "userSpaceOnUse",
          x1,
          x2,
          y1: railY,
          y2: railY,
        });
      function stops(from, to, members) {
        const colors = [
            ...new Set(members.map((id) => color(byId.get(id).a.label))),
          ].sort(),
          steps =
            colors.length === 1
              ? 1
              : colors.length *
                Math.min(
                  8,
                  Math.max(1, Math.floor((to - from) / (colors.length * 6))),
                );
        for (let i = 0; i < steps; i++) {
          for (const fraction of [i / steps, (i + 1) / steps])
            gradient.append(
              create("stop", {
                offset: Math.max(
                  0,
                  Math.min(1, (from + fraction * (to - from) - x1) / (x2 - x1)),
                ),
                class: `tower-bracket-color ${colors[i % colors.length]}`,
              }),
            );
        }
      }
      let previous = null,
        cursor = x1;
      for (const segment of region.segments) {
        const from = position(segment.start, false),
          to = position(segment.end, true);
        // SVG spacing between disjoint captions can lie inside an enclosing span.
        if (from > cursor && previous)
          stops(
            cursor,
            from,
            previous.ids.filter((id) => segment.ids.includes(id)),
          );
        stops(from, to, segment.ids);
        previous = segment;
        cursor = to;
      }
      defs.append(gradient);
      brackets.append(
        create("path", {
          d: `M ${x1} ${railY + 4} V ${railY} H ${x2} V ${railY + 4}`,
          class: "tower-bracket",
          stroke: `url(#${gradientId})`,
          "data-start": left + region.start,
          "data-end": left + region.end,
          "data-spans": JSON.stringify(
            ids.map((id) => {
              const p = byId.get(id);
              return { id, start: p.a.start, end: p.a.end, lane: p.lane };
            }),
          ),
          fill: "none",
        }),
      );
    });
    for (const p of parts) {
      const top = textY - bracketGap - 30 - p.labelHeight - laneOffset(p.lane);
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
            height: p.labelHeight,
            rx: 3,
            class: "tower-tag",
          }),
        );
        const caption = create("text", {
          x: p.center,
          y: top + 17,
          "text-anchor": "middle",
          class: "tower-caption",
        });
        p.captionLines.forEach((line, index) =>
          caption.append(
            create("tspan", { x: p.center, y: top + 17 + index * 14 }, line),
          ),
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
  // Every line includes its labels, focus/bracket gutters and trailing source.
  // Wrapping uses extra rows, never horizontal scrolling or compressed glyphs.
  svg.setAttribute("width", pixels);
  svg.setAttribute("height", y * scale);
  svg.setAttribute("viewBox", `0 0 ${width} ${y}`);
  host.scrollLeft = scroll.left;
  host.scrollTop = scroll.top;
}
