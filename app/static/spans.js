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
/** Keep graphemes intact for display; original annotation offsets remain untouched. */
export function readableSegments(
  text,
  start,
  annotations,
  originalParts = null,
) {
  const original = () => originalParts ?? segments(text, start, annotations);
  if (typeof Intl.Segmenter !== "function") return original();
  const boundaries = [start];
  for (const part of new Intl.Segmenter(undefined, {
    granularity: "grapheme",
  }).segment(text))
    boundaries.push(boundaries.at(-1) + Array.from(part.segment).length);
  const stop = boundaries.at(-1),
    exact = new Set(boundaries);
  if (
    annotations.every((a) => {
      const left = Math.max(start, a.start),
        right = Math.min(stop, a.end);
      return !(left < right) || (exact.has(left) && exact.has(right));
    })
  )
    return original();
  function boundary(value, up) {
    let lo = 0,
      hi = boundaries.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >>> 1;
      if (boundaries[mid] === value) return value;
      if (boundaries[mid] < value) lo = mid + 1;
      else hi = mid - 1;
    }
    return boundaries[up ? lo : hi];
  }
  const visual = annotations.flatMap((a) => {
    const left = Math.max(start, a.start),
      right = Math.min(stop, a.end);
    return left < right
      ? [{ ...a, start: boundary(left, false), end: boundary(right, true) }]
      : [];
  });
  return segments(text, start, visual);
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
export const ENTITY_COLORS = Object.freeze({
  DISEASE: "disease",
  SYMPTOM: "symptom",
  MEDICATION: "medication",
  PROCEDURE: "procedure",
  ANONYMIZATION: "anonymization",
  EVENT: "event",
  HUMAN: "human",
  LOCATION: "location",
  NEGATION_UNCERTAINTY: "negation",
  PROFESSION: "profession",
  SITUATION: "situation",
  SPECIES: "species",
  TEMPORALITY: "temporality",
});
const ALIASES = {
  ENFERMEDAD: "DISEASE",
  ENFERMEDADES: "DISEASE",
  MALALTIA: "DISEASE",
  DISEASES: "DISEASE",
  SINTOMA: "SYMPTOM",
  SÍNTOMA: "SYMPTOM",
  SÍMPTOMA: "SYMPTOM",
  MEDICAMENTO: "MEDICATION",
  FARMACO: "MEDICATION",
  DRUG: "MEDICATION",
  PROCEDIMIENTO: "PROCEDURE",
  PROCEDIMENT: "PROCEDURE",
  LOCALIZACION: "LOCATION",
  LOCALIZACIÓN: "LOCATION",
  UBICACION: "LOCATION",
  PERSON: "HUMAN",
  PERSONA: "HUMAN",
};
export function color(label) {
  const key = String(label).normalize("NFC").toUpperCase();
  return "entity-" + (ENTITY_COLORS[ALIASES[key] || key] || "other");
}
