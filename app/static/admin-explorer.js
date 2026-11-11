import { t, number, date, localized, onLocaleChange } from "./auth.js";
import { confirmDeletion } from "./deletion.js";

const base = document.querySelector('meta[name="app-prefix"]').content;
const tree = document.querySelector("#admin-explorer-tree");
const status = document.querySelector("#explorer-status");
const refreshButton = document.querySelector("#refresh-explorer");
const openNodes = new Set();
const expiryTimers = new Set();
let generation = 0,
  controller;
const make = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const part = encodeURIComponent;
async function api(path) {
  const response = await fetch(base + path, {
    cache: "no-store",
    signal: controller.signal,
  });
  if (response.status === 401)
    window.dispatchEvent(new Event("temu-session-expired"));
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      t(
        typeof data.detail === "string"
          ? data.detail
          : "The request could not be loaded.",
      ),
    );
  return data;
}
function link(label, path) {
  const node = make("a", t(label), "button secondary");
  node.href = localized(base + path);
  return node;
}
function distribution(title, values) {
  const entries = Object.entries(values || {});
  if (!entries.length) return null;
  const section = make("section", undefined, "explorer-distribution");
  section.append(make("h4", t(title)));
  const list = make("dl");
  for (const [key, value] of entries)
    list.append(
      make(
        "dt",
        t(
          {
            words: "Words",
            tokens: "Tokens",
            sentences: "Sentences",
            characters: "Characters",
          }[key] || key,
        ),
      ),
      make("dd", number(value)),
    );
  section.append(list);
  return section;
}
function statistics(values, scope = "") {
  const section = make("section", undefined, "explorer-summary");
  section.dataset.statisticsScope = scope;
  const metrics = make("dl", undefined, "explorer-counts");
  for (const [key, label] of [
    ["users", "Accounts"],
    ["projects", "Available projects"],
    ["expired_projects", "Expired projects"],
    ["documents", "Documents"],
    ["annotations", "Annotations"],
    ["entity_types", "Entity types"],
    ["normalizations", "Normalizations"],
    ["models_used", "Models"],
  ]) {
    if (values[key] === undefined || (key === "users" && scope !== "global"))
      continue;
    if (
      ["document", "project"].includes(scope) &&
      ["projects", "expired_projects"].includes(key)
    )
      continue;
    const item = make("div");
    item.dataset.statistic = key;
    item.append(make("dt", t(label)), make("dd", number(values[key])));
    metrics.append(item);
  }
  section.append(metrics);
  if (values.partial_projects || values.unavailable_documents)
    section.append(make("p", t("Partial statistics"), "notice"));
  const distributions = make("div", undefined, "explorer-distributions");
  for (const [key, title] of [
    ["documents_by_language", "Documents by language"],
    ["annotations_by_language", "Annotations by language"],
    ["entities_by_label", "Entity types"],
    ["annotations_by_model", "Annotations by model"],
    ["documents_by_model", "Models"],
    ["normalizations_by_label", "Concept normalization"],
    ["normalization_methods", "Normalization method"],
    ["normalization_languages", "Normalization languages"],
    ["document_states", "Documents"],
    ["job_states", "Projects"],
    ["text_statistics", "Text statistics"],
  ]) {
    const valuesForKey = Object.fromEntries(
      Object.entries(values[key] || {}).filter(([, v]) => v !== null),
    );
    const table = distribution(title, valuesForKey);
    if (table) distributions.append(table);
  }
  const breakdown = make("details", undefined, "explorer-breakdown");
  breakdown.append(
    make("summary", `${t("Entity types")} · ${t("Models")} · ${t("Language")}`),
    distributions,
  );
  section.append(breakdown);
  return section;
}
function restoreOpen(host) {
  for (const details of host.querySelectorAll("details[data-explorer-node]"))
    if (openNodes.has(details.dataset.explorerNode)) details.open = true;
}
function watchExpiry(project, serverNow) {
  if (project.expires_at == null) return;
  const deadline =
    performance.now() + Math.max(0, project.expires_at - serverNow) * 1000;
  const current = generation;
  function arm() {
    const timer = setTimeout(
      () => {
        expiryTimers.delete(timer);
        if (current !== generation) return;
        if (performance.now() < deadline) return arm();
        // Clear clinical surfaces immediately, before awaiting any network request.
        refresh();
      },
      Math.min(Math.max(0, deadline - performance.now()), 2147483647),
    );
    expiryTimers.add(timer);
  }
  arm();
}
function node(key, title, subtitle, load) {
  const li = make("li"),
    details = make("details", undefined, "explorer-node");
  details.dataset.explorerNode = key;
  const summary = make("summary");
  summary.append(make("span", title, "explorer-name"));
  if (subtitle) summary.append(make("small", subtitle));
  const panel = make("div", undefined, "explorer-panel");
  details.append(summary, panel);
  li.append(details);
  let loaded = false,
    loading = false;
  const current = generation;
  details.addEventListener("toggle", async () => {
    if (details.open) openNodes.add(key);
    else openNodes.delete(key);
    if (!details.open || loaded || loading) return;
    loading = true;
    panel.setAttribute("aria-busy", "true");
    panel.replaceChildren(make("p", t("Loading your workspace…")));
    try {
      const content = await load();
      if (current !== generation || !details.isConnected) return;
      panel.replaceChildren(...content);
      restoreOpen(panel);
      loaded = true;
    } catch (error) {
      if (error.name !== "AbortError" && current === generation)
        panel.replaceChildren(make("p", error.message, "notice"));
    } finally {
      loading = false;
      panel.removeAttribute("aria-busy");
    }
  });
  return li;
}
async function pages(
  path,
  render,
  onPage = () => {},
  emptyMessage = "No documents",
) {
  const wrapper = make("div"),
    list = make("ul", undefined, "explorer-children");
  wrapper.append(list);
  let offset = 0;
  const current = generation;
  const more = make("button", t("Load more"), "secondary");
  more.type = "button";
  async function load() {
    more.disabled = true;
    try {
      const data = await api(
        path +
          (path.includes("?") ? "&" : "?") +
          new URLSearchParams({ offset, limit: 25 }),
      );
      if (current !== generation) return;
      onPage(data);
      for (const item of data.items) list.append(render(item));
      if (list.isConnected) restoreOpen(list);
      offset += data.items.length;
      more.hidden = offset >= data.total;
      if (!offset) list.append(make("li", t(emptyMessage), "empty-state"));
    } finally {
      more.disabled = false;
    }
  }
  more.onclick = () =>
    load().catch((error) => {
      status.textContent = error.message;
    });
  await load();
  wrapper.append(more);
  return wrapper;
}
function deletionButton(label, endpoint, description, identity) {
  const button = make("button", t(label), "secondary destructive-text");
  button.type = "button";
  button.onclick = () =>
    confirmDeletion(
      endpoint,
      label,
      description,
      async () => {
        await refresh();
        refreshButton.focus();
      },
      (error) => {
        status.textContent = error;
      },
      (busy) => {
        button.disabled = busy;
      },
      undefined,
      identity,
    );
  return button;
}
function annotationTable() {
  const table = make("table", undefined, "responsive-table");
  const head = make("thead"),
    header = make("tr");
  for (const title of [
    "Annotation",
    "Start / end",
    "Models",
    "Concept normalization",
  ]) {
    const th = make("th", t(title));
    th.scope = "col";
    header.append(th);
  }
  head.append(header);
  table.append(head, make("tbody"));
  return table;
}
async function annotations(project, document) {
  const host = make("section");
  const details = make("details");
  details.open = true;
  details.append(make("summary", t("Annotations")));
  const table = annotationTable(),
    body = table.querySelector("tbody");
  details.append(table);
  host.append(details);
  const more = make("button", t("Load more"), "secondary");
  more.type = "button";
  details.append(more);
  let offset = 0,
    revision;
  const current = generation;
  async function load() {
    more.disabled = true;
    try {
      const data = await api(
        `/api/jobs/${part(project.id)}/documents/${part(document.document_id)}/annotations?offset=${offset}&limit=100`,
      );
      if (current !== generation) return;
      if (offset && revision !== data.revision) {
        offset = 0;
        body.replaceChildren();
        return load();
      }
      revision = data.revision;
      for (const item of data.items) {
        const row = make("tr");
        const normalized = item.normalization;
        const fields = [
          `${item.id} · ${item.label} · ${item.text}`,
          `[${item.start}, ${item.end})`,
          [
            ...new Set(
              [
                ...(item.model_ids || []),
                ...(item.sources || []).map((s) => s.model_id),
                item.model_id,
              ].filter(Boolean),
            ),
          ].join(", "),
          normalized
            ? `${normalized.code_system || ""}: ${normalized.code} · ${normalized.term}`
            : "—",
        ];
        fields.forEach((value, index) => {
          const cell = make("td", value);
          cell.dataset.label = t(
            ["Annotation", "Start / end", "Models", "Concept normalization"][
              index
            ],
          );
          row.append(cell);
        });
        body.append(row);
      }
      offset += data.items.length;
      more.hidden = offset >= data.total;
      if (!offset) host.append(make("p", t("No annotations")));
    } finally {
      more.disabled = false;
    }
  }
  more.onclick = () =>
    load().catch((error) => {
      status.textContent = error.message;
    });
  await load();
  return host;
}
function documentNode(project, document) {
  return node(
    "document:" + project.id + ":" + document.document_id,
    document.filename,
    `${t({ ANNOTATED: "COMPLETED", PENDING: "QUEUED" }[document.status] || document.status)} · ${number(document.statistics.annotations)} ${t("Annotations")}`,
    async () => {
      const controls = make("div", undefined, "action-row");
      controls.append(
        link(
          "Open viewer",
          `/jobs/${part(project.id)}/viewer?document=${part(document.document_id)}`,
        ),
      );
      if (document.original_available)
        controls.append(
          link(
            "Download TXT",
            `/api/jobs/${part(project.id)}/documents/${part(document.document_id)}/download/txt`,
          ),
        );
      controls.append(
        link(
          "Download ANN",
          `/api/jobs/${part(project.id)}/documents/${part(document.document_id)}/download/ann`,
        ),
      );
      controls.append(
        deletionButton(
          "Delete document",
          `/api/jobs/${part(project.id)}/documents/${part(document.document_id)}`,
          "This deletes only the selected documents and their annotations and frees your quota. Upload history remains.",
          `${project.name} · ${document.filename}`,
        ),
      );
      return [
        statistics(document.statistics, "document"),
        controls,
        await annotations(project, document),
      ];
    },
  );
}
function projectNode(project) {
  return node(
    "project:" + project.id,
    project.name,
    `${(project.language || "—").toUpperCase()} · ${t(project.status)}`,
    async () => {
      const controls = make("div", undefined, "action-row");
      controls.append(
        deletionButton(
          "Delete project",
          `/api/admin/projects/${part(project.id)}`,
          "Delete this project and all its documents and annotations?",
          `${project.name} · ${project.id}`,
        ),
      );
      if (!project.available)
        return [make("p", t("Results have expired."), "notice"), controls];
      let snapshot;
      const documents = await pages(
        `/api/admin/explorer/projects/${part(project.id)}`,
        (item) => documentNode(project, item),
        (data) => {
          snapshot = data;
        },
      );
      controls.prepend(link("open", `/jobs/${part(project.id)}`));
      if (
        ["COMPLETED", "COMPLETED_WITH_ERRORS"].includes(snapshot.project.status)
      )
        controls.append(
          link("Download BRAT", `/api/jobs/${part(project.id)}/download/brat`),
          link("Download TSV", `/api/jobs/${part(project.id)}/download/tsv`),
          link(
            "Download statistics (.json)",
            `/api/jobs/${part(project.id)}/statistics`,
          ),
        );
      watchExpiry(snapshot.project, snapshot.updated_at);
      const modelList = make("section");
      modelList.append(make("h4", t("Models")));
      for (const model of snapshot.model_execution)
        modelList.append(
          make(
            "p",
            `${model.model_id} · ${t(model.status)} · ${number(model.completed_documents)} / ${number(model.total_documents)}`,
          ),
        );
      const heading = make("h4", t("Documents"));
      return [
        statistics(snapshot.statistics, "project"),
        controls,
        modelList,
        heading,
        documents,
      ];
    },
  );
}
function userNode(user) {
  const name =
    user.id === "unassigned" ? t("Unassigned owner") : user.full_name;
  return node("user:" + user.id, name, user.email, async () => {
    let snapshot;
    const projects = await pages(
      `/api/admin/explorer/users/${part(user.id)}/projects`,
      projectNode,
      (data) => {
        snapshot = data;
      },
      "No projects found.",
    );
    const metadata = make(
      "p",
      [user.email, user.institution].filter(Boolean).join(" · "),
    );
    const details = make("details");
    details.open = true;
    details.append(make("summary", t("Projects")), projects);
    return [metadata, statistics(snapshot.statistics, "user"), details];
  });
}
async function refresh() {
  controller?.abort();
  for (const timer of expiryTimers) clearTimeout(timer);
  expiryTimers.clear();
  tree.replaceChildren();
  document.querySelector("#explorer-statistics").replaceChildren();
  controller = new AbortController();
  const current = ++generation;
  refreshButton.disabled = true;
  tree.setAttribute("aria-busy", "true");
  status.textContent = t("Loading your workspace…");
  try {
    const [overview, users] = await Promise.all([
      api("/api/admin/explorer/statistics"),
      pages("/api/admin/explorer/users", userNode),
    ]);
    if (current !== generation) return;
    document
      .querySelector("#explorer-statistics")
      .replaceChildren(statistics(overview.statistics, "global"));
    const root = make("details");
    root.open = true;
    root.append(
      make(
        "summary",
        `${t("All users")} · ${number(overview.statistics.users)}`,
      ),
      users,
    );
    tree.replaceChildren(root);
    restoreOpen(tree);
    status.textContent = date(
      new Date(overview.updated_at * 1000).toISOString(),
    );
  } catch (error) {
    if (error.name !== "AbortError" && current === generation) {
      tree.replaceChildren();
      status.textContent = error.message;
    }
  } finally {
    if (current === generation) {
      refreshButton.disabled = false;
      tree.removeAttribute("aria-busy");
    }
  }
}
refreshButton.onclick = refresh;
onLocaleChange(refresh);
window.addEventListener("pagehide", () => {
  controller?.abort();
  for (const timer of expiryTimers) clearTimeout(timer);
});
refresh();
