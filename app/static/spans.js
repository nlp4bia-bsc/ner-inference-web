/** Rendering coordinates use Unicode code points, never JS UTF-16 indices. */
export function segments(text, start, annotations) {
  const points = Array.from(text),
    stop = start + points.length;
  const events = new Map([
    [start, { add: [], remove: [] }],
    [stop, { add: [], remove: [] }],
  ]);
  const event = (x) => {
    if (!events.has(x)) events.set(x, { add: [], remove: [] });
    return events.get(x);
  };
  for (const a of annotations) {
    const left = Math.max(start, a.start),
      right = Math.min(stop, a.end);
    if (left < right) {
      event(left).add.push(a.id);
      event(right).remove.push(a.id);
    }
  }
  const boundaries = [...events.keys()].sort((a, b) => a - b),
    active = new Set(),
    result = [];
  for (let i = 0; i < boundaries.length - 1; i++) {
    const left = boundaries[i],
      right = boundaries[i + 1],
      e = events.get(left);
    for (const id of e.remove) active.delete(id);
    for (const id of e.add) active.add(id);
    result.push({
      start: left,
      end: right,
      text: points.slice(left - start, right - start).join(""),
      ids: [...active],
    });
  }
  return result;
}
export function lanes(annotations) {
  const ends = [],
    result = new Map();
  for (const a of [...annotations].sort(
    (a, b) => a.start - b.start || b.end - a.end || a.id.localeCompare(b.id),
  )) {
    let lane = ends.findIndex((x) => x <= a.start);
    if (lane < 0) lane = ends.length;
    ends[lane] = a.end;
    result.set(a.id, lane);
  }
  return result;
}
export function color(label) {
  let hash = 0;
  for (const point of label) hash = (hash * 31 + point.codePointAt(0)) >>> 0;
  return "c" + (hash % 8);
}
