import { startProgress, showDialog } from "./progress.js";
import { segments, lanes, color } from "./spans.js";
const base = document.querySelector("meta[name=app-prefix]").content;
const token = location.pathname.split("/").at(-2),
  endpoint = base + "/api/jobs/" + encodeURIComponent(token);
const $ = (id) => document.getElementById(id);
let records = [],
  docOffset = 0,
  docTotal = 0,
  identity = null,
  chunk = null,
  annotations = [],
  enabled = new Set(),
  selected = null,
  mentionOffset = 0,
  generation = 0,
  expiryTimer,
  listGeneration = 0,
  expiresAt = Infinity,
  expired = false;
const make = (tag, text, cls) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
};
async function api(path) {
  const response = await fetch(endpoint + path, { cache: "no-store" });
  const data = await response.json();
  if (expired) {
    expire();
    throw new Error("Results have expired.");
  }
  if (response.status === 401)
    window.dispatchEvent(new Event("temu-session-expired"));
  if (response.status === 410) {
    expire();
    throw new Error("Results have expired.");
  }
  if (!response.ok)
    throw new Error(data.detail || "The request could not be loaded.");
  return data;
}
function failure(error) {
  $("viewer-status").textContent = error.message;
}
function expire() {
  expired = true;
  $("entity-sheet-trigger").hidden = true;
  document.querySelectorAll("dialog").forEach((dialog) => dialog.close());
  generation++;
  identity = null;
  annotations = [];
  records = [];
  selected = null;
  enabled.clear();
  getSelection()?.removeAllRanges();
  chunk = null;
  for (const id of [
    "annotated-text",
    "annotation-list",
    "annotation-details",
    "region-annotations",
    "document-list",
    "metrics",
    "annotation-table-body",
    "document-stats",
    "filename",
    "job-distribution",
  ])
    $(id).replaceChildren();
  $("viewer-status").textContent =
    "Your results have expired. Documents are no longer available.";
  $("download-link").removeAttribute("href");
  $("individual-txt").removeAttribute("href");
  $("individual-ann").removeAttribute("href");
  document
    .querySelectorAll("main button,main input,main select")
    .forEach((x) => (x.disabled = true));
  clearTimeout(expiryTimer);
}
const safely =
  (fn) =>
  (...args) =>
    Promise.resolve(fn(...args)).catch(failure);
const debounce = (fn) => {
  let timer;
  return () => {
    clearTimeout(timer);
    timer = setTimeout(safely(fn), 200);
  };
};
async function documents() {
  const query = new URLSearchParams({
    offset: docOffset,
    limit: 50,
    q: $("document-search").value,
  });
  if ($("document-filter").value)
    query.set("has_annotations", $("document-filter").value);
  const requestGeneration = ++listGeneration;
  const scroll = $("document-list").scrollTop;
  if ($("document-state")?.value)
    query.set("status", $("document-state").value);
  if ($("document-sort")?.checked) query.set("sort", "name");
  const data = await api("/documents?" + query);
  if (requestGeneration !== listGeneration) return;
  records = data.items;
  docTotal = data.total;
  $("document-total").textContent = data.total;
  $("document-list").replaceChildren();
  for (const row of records) {
    const button = make(
      "button",
      undefined,
      "document-item" + (row.document_id === identity ? " active" : ""),
    );
    button.append(
      make("strong", row.filename),
      make(
        "small",
        row.annotation_count
          ? `${row.annotation_count} mentions`
          : "No annotations",
      ),
    );
    button.dataset.document = row.document_id;
    button.disabled = !["ANNOTATED", "COMPLETED"].includes(row.status);
    button.querySelector("small").textContent =
      `${row.status} · ${row.annotation_count} mentions`;
    button.onclick = safely(() => openDocument(row.document_id));
    $("document-list").append(button);
  }
  $("doc-page").textContent = docTotal
    ? `${docOffset + 1}–${Math.min(docTotal, docOffset + 50)} / ${docTotal}`
    : "No documents";
  $("docs-prev").disabled = docOffset === 0;
  $("docs-next").disabled = docOffset + 50 >= docTotal;
  buildTree();
  $("document-list").scrollTop = scroll;
  const available = records.find((r) =>
    ["ANNOTATED", "COMPLETED"].includes(r.status),
  );
  if (!identity && available) await openDocument(available.document_id);
}
async function openDocument(id, start = 0) {
  const current = ++generation;
  identity = id;
  selected = null;
  mentionOffset = 0;
  $("text-search").value = "";
  $("region-annotations").replaceChildren();
  $("annotation-details").replaceChildren(
    make(
      "p",
      "Select a mention to inspect its original offsets and model.",
      "quiet",
    ),
  );
  $("viewer-status").textContent = "Loading document…";
  const text = await api(`/documents/${id}?start=${start}&limit=5000`);
  if (current !== generation) return;
  const rows = [];
  let offset = 0,
    total;
  do {
    const page = await api(
      `/documents/${id}/annotations?start=${text.start}&end=${text.end}&offset=${offset}&limit=500`,
    );
    if (current !== generation) return;
    rows.push(...page.items);
    total = page.total;
    offset += page.items.length;
  } while (offset < total);
  const stats = await api(`/documents/${id}/statistics`);
  if (current !== generation) return;
  chunk = text;
  annotations = rows;
  enabled = new Set(rows.map((x) => x.label));
  $("entity-search").value = "";
  $("filename").textContent = text.filename;
  $("individual-txt").href = endpoint + "/documents/" + id + "/download/txt";
  $("individual-ann").href = endpoint + "/documents/" + id + "/download/ann";
  $("chunk-info").textContent =
    `Characters ${text.start}–${text.end} of ${text.total_characters} · original Unicode code-point offsets`;
  $("chunk-prev").disabled = text.start === 0;
  $("chunk-next").disabled = text.end >= text.total_characters;
  $("document-stats").textContent = Object.entries(stats.statistics)
    .filter(([k]) =>
      ["words", "tokens", "sentences", "entities_total"].includes(k),
    )
    .map(([k, v]) => `${k.replace("_total", "")}: ${v ?? "unavailable"}`)
    .join(" · ");
  $("legend").replaceChildren();
  for (const label of [...enabled].sort()) {
    const container = make("label", undefined, "entity-toggle " + color(label)),
      input = make("input"),
      name = make(
        "span",
        `${label} · ${rows.filter((x) => x.label === label).length}`,
      );
    input.type = "checkbox";
    input.checked = true;
    input.onchange = () => {
      input.checked ? enabled.add(label) : enabled.delete(label);
      mentionOffset = 0;
      render();
    };
    container.append(input, name);
    $("legend").append(container);
  }
  $("document-list")
    .querySelectorAll("button")
    .forEach((button, i) =>
      button.classList.toggle("active", button.dataset.document === id),
    );
  render();
  $("viewer-status").textContent =
    "Read-only exploration · select a highlighted region or an annotation.";
}
function visible() {
  const query = $("entity-search").value.toLocaleLowerCase();
  return annotations.filter(
    (x) => enabled.has(x.label) && x.text.toLocaleLowerCase().includes(query),
  );
}
function render() {
  if (!chunk) return;
  const rows = visible(),
    byId = new Map(rows.map((a) => [a.id, a])),
    fragment = document.createDocumentFragment();
  for (const part of segments(chunk.text, chunk.start, rows)) {
    if (!part.ids.length) {
      fragment.append(document.createTextNode(part.text));
      continue;
    }
    const a = byId.get(part.ids[0]),
      span = make("span", part.text, "annotated " + color(a.label));
    span.dataset.ids = part.ids.join(" ");
    span.dataset.start = part.start;
    span.dataset.count = part.ids.length > 1 ? part.ids.length : "";
    span.tabIndex = 0;
    span.setAttribute("role", "button");
    span.setAttribute(
      "aria-label",
      `${part.text}: ${part.ids.length} annotation(s), ${part.ids.map((id) => byId.get(id).label).join(", ")}`,
    );
    const activate = () => {
      const choices = make("div");
      choices.append(
        make("strong", `${part.ids.length} annotation(s) in this region`),
      );
      for (const id of part.ids) {
        const button = make(
          "button",
          `${byId.get(id).label} · ${id}`,
          "secondary " + color(byId.get(id).label),
        );
        button.onclick = () => select(id);
        choices.append(button);
      }
      $("region-annotations").replaceChildren(choices);
      select(part.ids[0]);
    };
    span.onclick = activate;
    span.onkeydown = (event) => {
      if (["Enter", " "].includes(event.key)) {
        event.preventDefault();
        activate();
      }
    };
    fragment.append(span);
  }
  $("annotated-text").replaceChildren(fragment);
  renderList(rows);
  highlight();
}
function renderList(rows) {
  const levels = lanes(rows);
  $("annotation-list").replaceChildren();
  for (const row of rows.slice(mentionOffset, mentionOffset + 50)) {
    const button = make("button", undefined, "mention " + color(row.label));
    button.dataset.annotation = row.id;
    button.append(
      make(
        "strong",
        Array.from(row.text.slice(0, 320)).slice(0, 160).join("") +
          (Array.from(row.text.slice(0, 322)).length > 160 ? "…" : ""),
      ),
      make(
        "span",
        `${row.label} · ${row.start}–${row.end} · lane ${levels.get(row.id) + 1}`,
      ),
    );
    button.onclick = () => select(row.id, true);
    $("annotation-list").append(button);
  }
  renderTable(rows.slice(mentionOffset, mentionOffset + 50));
  $("mention-page").textContent = `${rows.length} mentions`;
  $("mentions-prev").disabled = mentionOffset === 0;
  $("mentions-next").disabled = mentionOffset + 50 >= rows.length;
  $("entity-position").textContent = selected
    ? `${rows.findIndex((x) => x.id === selected) + 1} / ${rows.length}`
    : `${rows.length} mentions`;
}
function select(id, scroll = false) {
  const a = annotations.find((x) => x.id === id);
  if (!a) return;
  selected = id;
  $("entity-sheet-trigger").hidden = !matchMedia("(max-width:760px)").matches;
  const selectedIndex = visible().findIndex((x) => x.id === id);
  if (selectedIndex >= 0) mentionOffset = Math.floor(selectedIndex / 50) * 50;
  const heading = make("h3", a.label, "entity-badge " + color(a.label)),
    surface = make("blockquote", a.text),
    list = make("dl");
  for (const [name, value] of [
    ["Annotation", a.id],
    ["Start / end", `${a.start} / ${a.end}`],
    [
      "Model",
      (a.model_ids?.length ? a.model_ids.join(", ") : a.model_id) ||
        "Not provided",
    ],
    ["Original sublabels", a.original_labels?.join(", ") || a.label],
    ["Model version", a.model_version || "Not provided"],
    [
      "Overlaps",
      annotations
        .filter((b) => b.id !== a.id && b.start < a.end && b.end > a.start)
        .map((b) => b.id + " " + b.label)
        .join(", ") || "None",
    ],
    ["Confidence", a.score === null ? "Not provided" : a.score.toFixed(4)],
  ])
    list.append(make("dt", name), make("dd", value));
  const copy = make("button", "Copy entity", "secondary");
  copy.onclick = safely(() => navigator.clipboard.writeText(a.text));
  const offsets = make("button", "Copy offsets", "secondary");
  offsets.onclick = safely(() =>
    navigator.clipboard.writeText(`${a.start}\t${a.end}`),
  );
  $("annotation-details").replaceChildren(
    heading,
    surface,
    list,
    sourceDetails(a),
    copy,
    offsets,
  );
  highlight();
  renderList(visible());
  if (scroll) {
    const node = [...$("annotated-text").querySelectorAll("[data-ids]")].find(
      (x) => x.dataset.ids.split(" ").includes(id),
    );
    node?.scrollIntoView({ block: "center" });
  }
}
function highlight() {
  for (const node of $("annotated-text").querySelectorAll("[data-ids]")) {
    const match = node.dataset.ids.split(" ").includes(selected);
    node.classList.toggle("selected", match);
    node.classList.toggle("dimmed", Boolean(selected) && !match);
  }
}
function navigate(direction) {
  const rows = visible();
  if (!rows.length) return;
  const index = rows.findIndex((x) => x.id === selected);
  const target =
    index < 0
      ? direction > 0
        ? 0
        : rows.length - 1
      : (index + direction + rows.length) % rows.length;
  mentionOffset = Math.floor(target / 50) * 50;
  select(rows[target].id, true);
}
$("entity-prev").onclick = () => navigate(-1);
$("entity-next").onclick = () => navigate(1);
$("mentions-prev").onclick = () => {
  mentionOffset = Math.max(0, mentionOffset - 50);
  renderList(visible());
};
$("mentions-next").onclick = () => {
  mentionOffset += 50;
  renderList(visible());
};
$("entity-search").oninput = () => {
  mentionOffset = 0;
  selected = null;
  $("region-annotations").replaceChildren();
  render();
};
$("document-search").oninput = debounce(() => {
  docOffset = 0;
  return documents();
});
$("document-filter").onchange = safely(() => {
  docOffset = 0;
  return documents();
});
$("docs-prev").onclick = safely(() => {
  docOffset = Math.max(0, docOffset - 50);
  return documents();
});
$("docs-next").onclick = safely(() => {
  docOffset += 50;
  return documents();
});
$("chunk-prev").onclick = safely(() =>
  openDocument(identity, Math.max(0, chunk.start - 5000)),
);
$("chunk-next").onclick = safely(() => openDocument(identity, chunk.end));
let searchAfter = 0,
  previousQuery = "",
  searchDocument = null;
$("find-next").onclick = safely(async () => {
  if (!chunk) return;
  const query = $("text-search").value;
  if (!query) return;
  const documentId = identity;
  if (previousQuery !== query || searchDocument !== identity) searchAfter = 0;
  const match = await api(
    `/documents/${identity}/search?` +
      new URLSearchParams({ q: query, start: searchAfter }),
  );
  if (documentId !== identity) return;
  if (match.start === null) {
    $("viewer-status").textContent = "No matches in this document.";
    return;
  }
  if (match.start < chunk.start || match.end > chunk.end)
    await openDocument(documentId, match.start);
  if (documentId !== identity) return;
  $("text-search").value = query;
  previousQuery = query;
  searchDocument = identity;
  searchAfter = match.end;
  render();
  const start = match.start - chunk.start,
    end = match.end - chunk.start,
    walker = document.createTreeWalker(
      $("annotated-text"),
      NodeFilter.SHOW_TEXT,
    );
  let node,
    position = 0,
    first,
    last;
  while ((node = walker.nextNode())) {
    const length = Array.from(node.textContent).length;
    if (!first && position + length > start)
      first = {
        node,
        offset: Array.from(node.textContent)
          .slice(0, start - position)
          .join("").length,
      };
    if (position + length >= end) {
      last = {
        node,
        offset: Array.from(node.textContent)
          .slice(0, end - position)
          .join("").length,
      };
      break;
    }
    position += length;
  }
  if (first && last) {
    const range = document.createRange();
    range.setStart(first.node, first.offset);
    range.setEnd(last.node, last.offset);
    const selection = getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    first.node.parentElement.scrollIntoView({ block: "center" });
  }
  $("viewer-status").textContent =
    `Text match at ${match.start}–${match.end} · ${match.total} match(es) in this document.`;
});
$("results-link").href = base + "/jobs/" + token;
$("download-link").href = endpoint + "/download/brat";
safely(async () => {
  const job = await api("");
  $("viewer-expiry").textContent =
    "Available until " +
    (job.expires_at
      ? new Date(job.expires_at).toLocaleString()
      : "after processing finishes");
  if (job.expires_at)
    expiresAt =
      Date.now() + Date.parse(job.expires_at) - Date.parse(job.server_now);
  for (const [label, key] of [
    ["Documents", "documents"],
    ["Words", "words"],
    ["Tokens", "tokens"],
    ["Sentences", "sentences"],
    ["Entities", "annotations"],
  ]) {
    const card = make("div");
    card.append(
      make(
        "strong",
        job.summary?.[key] ?? (key === "documents" ? job.document_count : "—"),
      ),
      make("span", label),
    );
    $("metrics").append(card);
  }
  const distribution = $("job-distribution");
  distribution.append(make("strong", "Corpus distribution"));
  for (const [label, count] of Object.entries(
    job.summary?.mentions_by_label || {},
  )) {
    distribution.append(
      make("span", `${label} · ${count}`, "entity-toggle " + color(label)),
    );
  }
  await documents();
})();

async function navigateDocument(direction) {
  let index = records.findIndex((x) => x.document_id === identity) + direction;
  if (index >= 0 && index < records.length)
    return openDocument(records[index].document_id);
  const next = docOffset + direction * 50;
  if (next < 0 || next >= docTotal) return;
  docOffset = next;
  await documents();
  if (records.length)
    return openDocument(
      records[direction > 0 ? 0 : records.length - 1].document_id,
    );
}
$("document-prev").onclick = safely(() => navigateDocument(-1));
$("document-next").onclick = safely(() => navigateDocument(1));

const folderState = new Map();
function buildTree() {
  const list = $("document-list"),
    buttons = [...list.querySelectorAll("button")],
    folders = new Map();
  list.replaceChildren();
  for (const button of buttons) {
    const filename =
      records.find((r) => r.document_id === button.dataset.document)
        ?.filename || "";
    const parts = filename.split("/");
    let parent = list,
      path = "";
    for (const part of parts.slice(0, -1)) {
      path += (path ? "/" : "") + part;
      if (!folders.has(path)) {
        const branch = make("details"),
          summary = make("summary", part);
        branch.open = folderState.get(path) ?? true;
        const key = path;
        branch.ontoggle = () => folderState.set(key, branch.open);
        branch.append(summary);
        parent.append(branch);
        folders.set(path, branch);
      }
      parent = folders.get(path);
    }
    button.title = filename;
    button.querySelector("strong").textContent = parts.at(-1);
    parent.append(button);
  }
}
function renderTable(rows) {
  const body = $("annotation-table-body");
  if (!body) return;
  body.replaceChildren();
  for (const a of rows) {
    const row = make("tr");
    row.dataset.tableAnnotation = a.id;
    row.setAttribute("aria-selected", String(a.id === selected));
    const first = make("td"),
      button = make(
        "button",
        Array.from(a.text.slice(0, 200)).slice(0, 100).join(""),
      );
    button.type = "button";
    button.onclick = () => select(a.id, true);
    first.append(button);
    row.append(first);
    for (const value of [
      a.label,
      a.start,
      a.end,
      a.score === null ? "—" : a.score,
      (a.model_ids?.length ? a.model_ids.join(", ") : a.model_id) || "—",
    ])
      row.append(make("td", String(value)));
    body.append(row);
  }
}
let lastProgressKey = "";
startProgress(endpoint, {
  onExpire: expire,
  onChange: async (snapshot) => {
    if (snapshot.expires_at)
      expiresAt =
        Date.now() +
        Date.parse(snapshot.expires_at) -
        Date.parse(snapshot.server_now);
    $("download-link").hidden = ![
      "COMPLETED",
      "COMPLETED_WITH_ERRORS",
    ].includes(snapshot.status);
    const cards = $("metrics").children;
    const provisional = snapshot.provisional_statistics || {};
    const values = [
      snapshot.total_documents,
      provisional.words,
      provisional.tokens,
      provisional.sentences,
      snapshot.mentions,
    ];
    for (let i = 0; i < cards.length; i++)
      cards[i].querySelector("strong").textContent = values[i] ?? "—";
    $("metrics-scope").textContent =
      snapshot.status === "COMPLETED"
        ? "Final statistics"
        : snapshot.status === "COMPLETED_WITH_ERRORS"
          ? "Final statistics for annotated documents; failed documents excluded"
          : "Provisional statistics: annotated documents only";
    const key = [
      snapshot.annotated_documents,
      snapshot.failed_documents,
      snapshot.processing_documents,
      snapshot.status,
    ].join(":");
    if (key !== lastProgressKey) {
      lastProgressKey = key;
      await documents();
    }
  },
});
$("document-state").onchange = safely(() => {
  docOffset = 0;
  return documents();
});
$("document-sort").onchange = safely(() => {
  docOffset = 0;
  return documents();
});
document.addEventListener("keydown", (event) => {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
  if (event.key === "ArrowRight" && event.altKey) {
    event.preventDefault();
    navigate(1);
  }
  if (event.key === "ArrowLeft" && event.altKey) {
    event.preventDefault();
    navigate(-1);
  }
});

function showEntitySheet(id) {
  const a = annotations.find((row) => row.id === id);
  if (!a) return;
  const dialog = showDialog(a.label, a.text, [
    { label: "Copy entity", run: () => navigator.clipboard.writeText(a.text) },
  ]);
  dialog.classList.add("entity-sheet");
  const offsets = make(
    "p",
    `Offsets ${a.start}–${a.end} · ${a.model_id || "Model not provided"} · confidence ${a.score ?? "not provided"}`,
  );
  dialog.append(offsets, sourceDetails(a));
  for (const other of annotations.filter(
    (row) => row.id !== a.id && row.start < a.end && row.end > a.start,
  )) {
    const button = make("button", `${other.id} · ${other.label}`, "secondary");
    button.onclick = () => {
      dialog.close();
      select(other.id);
      showEntitySheet(other.id);
    };
    dialog.append(button);
  }
}

$("entity-sheet-trigger").onclick = () => showEntitySheet(selected);

function sourceDetails(annotation) {
  const details = make("div", "", "annotation-sources");
  if (!annotation.sources?.length) return details;
  details.append(make("h4", "Supporting predictions"));
  for (const source of annotation.sources) {
    const row = make("p");
    row.append(make("strong", source.model_id));
    row.append(
      document.createTextNode(
        ` · ${source.model_version || "version not provided"} · ${source.original_label} · score ${source.score ?? "not provided"}`,
      ),
    );
    details.append(row);
  }
  return details;
}
