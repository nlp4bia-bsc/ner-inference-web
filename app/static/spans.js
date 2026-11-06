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
// Display aliases only; scientific labels/mappings are never rewritten here.
// Raw PROFESION is ambiguous across schemas; canonical ANONYMIZATION stays distinct.
const ALIASES = Object.freeze({
  AGE: "TEMPORALITY",
  ANONIMITZACIO: "ANONYMIZATION",
  ANONIMIZACION: "ANONYMIZATION",
  ANONYMISATION: "ANONYMIZATION",
  ATENCION: "LOCATION",
  CALLE: "ANONYMIZATION",
  CENTRO_SALUD: "ANONYMIZATION",
  COMUNIDAD: "LOCATION",
  CORREO_ELECTRONICO: "ANONYMIZATION",
  DATE: "TEMPORALITY",
  DEPARTAMENTO: "LOCATION",
  DISEASES: "DISEASE",
  DRUG: "MEDICATION",
  DRUGS: "MEDICATION",
  DURATION: "TEMPORALITY",
  EDAD_SUJETO_ASISTENCIA: "ANONYMIZATION",
  ENFERMEDAD: "DISEASE",
  ENFERMEDADES: "DISEASE",
  ESPECIE: "SPECIES",
  ESPECIES: "SPECIES",
  FAC_GEN: "LOCATION",
  FAC_NOM: "LOCATION",
  FAMILIARES_SUJETO_ASISTENCIA: "ANONYMIZATION",
  FARMAC: "MEDICATION",
  FARMACO: "MEDICATION",
  FARMACS: "MEDICATION",
  FECHAS: "ANONYMIZATION",
  GEO_GEN: "LOCATION",
  GEO_NOM: "LOCATION",
  GPE_GEN: "LOCATION",
  GPE_NOM: "LOCATION",
  HOSPITAL: "ANONYMIZATION",
  HUMANO: "HUMAN",
  HUMANS: "HUMAN",
  IDIOMA: "LOCATION",
  ID_ASEGURAMIENTO: "ANONYMIZATION",
  ID_CONTACTO_ASISTENCIAL: "ANONYMIZATION",
  ID_SUJETO_ASISTENCIA: "ANONYMIZATION",
  ID_TITULACION_PERSONAL_SANITARIO: "ANONYMIZATION",
  INCERTESA: "NEGATION_UNCERTAINTY",
  INCERTIDUMBRE: "NEGATION_UNCERTAINTY",
  INSTITUCION: "ANONYMIZATION",
  LOC: "LOCATION",
  LOCALIZACIO: "LOCATION",
  LOCALIZACION: "LOCATION",
  LOCATIONS: "LOCATION",
  LUGAR_NATAL: "LOCATION",
  MALALTIA: "DISEASE",
  MALALTIES: "DISEASE",
  MEDICAMENT: "MEDICATION",
  MEDICAMENTO: "MEDICATION",
  MEDICAMENTOS: "MEDICATION",
  MEDICAMENTS: "MEDICATION",
  MEDICATIONS: "MEDICATION",
  MOVIMIENTO: "LOCATION",
  NEG: "NEGATION_UNCERTAINTY",
  NEGACIO: "NEGATION_UNCERTAINTY",
  NEGACION: "NEGATION_UNCERTAINTY",
  NEGATION: "NEGATION_UNCERTAINTY",
  NOMBRE_PERSONAL_SANITARIO: "ANONYMIZATION",
  NOMBRE_SUJETO_ASISTENCIA: "ANONYMIZATION",
  NSCO: "NEGATION_UNCERTAINTY",
  NUMERO_FAX: "ANONYMIZATION",
  NUMERO_TELEFONO: "ANONYMIZATION",
  OTHER: "LOCATION",
  OTROS_SUJETO_ASISTENCIA: "ANONYMIZATION",
  PAIS: "ANONYMIZATION",
  PERSON: "HUMAN",
  PERSONA: "HUMAN",
  PROCEDIMENT: "PROCEDURE",
  PROCEDIMENTS: "PROCEDURE",
  PROCEDIMIENTO: "PROCEDURE",
  PROCEDIMIENTOS: "PROCEDURE",
  PROCEDURES: "PROCEDURE",
  PROFESION: "PROFESSION",
  PROFESSIO: "PROFESSION",
  PROFESSIONS: "PROFESSION",
  RESIDENCIA: "LOCATION",
  SET: "TEMPORALITY",
  SEXO_SUJETO_ASISTENCIA: "ANONYMIZATION",
  SIMPTOMA: "SYMPTOM",
  SIMPTOMES: "SYMPTOM",
  SINTOMA: "SYMPTOM",
  SINTOMAS: "SYMPTOM",
  SITUACION_LABORAL: "PROFESSION",
  SYMPTOMS: "SYMPTOM",
  TEMPORALIDAD: "TEMPORALITY",
  TEMPORALITAT: "TEMPORALITY",
  TERRITORIO: "ANONYMIZATION",
  TIME: "TEMPORALITY",
  TRANSPORTE: "LOCATION",
  UBICACIO: "LOCATION",
  UBICACION: "LOCATION",
  UNC: "NEGATION_UNCERTAINTY",
  UNCERTAINTY: "NEGATION_UNCERTAINTY",
  USCO: "NEGATION_UNCERTAINTY",
});
export const CUSTOM_COLOR_COUNT = 24;
export function color(label) {
  const key = String(label)
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .trim()
    .toUpperCase()
    .replace(/^(?:B|I|E|S|U|L)[-_]/u, "")
    .replace(/[\s/-]+/gu, "_");
  const category = ALIASES[key] || key;
  if (Object.hasOwn(ENTITY_COLORS, category))
    return "entity-" + ENTITY_COLORS[category];
  let hash = 2166136261;
  for (const point of key)
    hash = Math.imul(hash ^ point.codePointAt(0), 16777619) >>> 0;
  return "entity-custom-" + (hash % CUSTOM_COLOR_COUNT);
}
