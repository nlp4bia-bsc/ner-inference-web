import { t, number, date, localized, onLocaleChange } from "./auth.js";
import { paintQuota } from "./quota.js";
import { confirmDeletion } from "./deletion.js";
const base = document.querySelector('meta[name="app-prefix"]').content;
const tbody = document.querySelector("#document-history");
const message = document.querySelector("#management-message");
const filter = document.querySelector("#document-filter");
const selected = new Map();
const selectionCount = document.querySelector("#document-selection-count"),
  selectVisible = document.querySelector("#select-visible-documents"),
  deleteSelected = document.querySelector("#delete-selected-documents");
const job = new URL(location.href).searchParams.get("job");
let offset = 0,
  total = 0,
  records = [],
  busy = false;
function render() {
  tbody.replaceChildren();
  for (const row of records) {
    const tr = document.createElement("tr");
    const selection = document.createElement("td"),
      checkbox = document.createElement("input");
    selection.className = "document-selection";
    selection.dataset.label = t("Select document");
    checkbox.type = "checkbox";
    checkbox.dataset.selectDocument = row.id;
    checkbox.setAttribute(
      "aria-label",
      t("Select document") + ": " + row.filename,
    );
    if (row.state !== "STORED") selected.delete(row.id);
    checkbox.checked = selected.has(row.id);
    checkbox.disabled = busy || row.state !== "STORED";
    checkbox.onchange = () => {
      checkbox.checked
        ? selected.set(row.id, {
            job_id: row.job_id,
            document_id: row.document_id,
          })
        : selected.delete(row.id);
      updateSelection();
    };
    selection.append(checkbox);
    tr.append(selection);
    for (const [label, value] of [
      ["Document", row.filename],
      ["Uploaded", date(new Date(row.uploaded_at * 1000))],
      ["Language", row.language === "oth" ? "OTH" : row.language || "—"],
      ["status", t(row.state)],
    ]) {
      const td = document.createElement("td");
      td.dataset.label = t(label);
      td.textContent = value;
      tr.append(td);
    }
    const actions = document.createElement("td");
    actions.dataset.label = t("Actions");
    if (row.state === "STORED") {
      const link = document.createElement("a");
      link.href = localized(base + "/jobs/" + row.job_id);
      link.textContent = t("Open job");
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "secondary destructive-text";
      remove.textContent = t("Delete document");
      remove.disabled = busy;
      remove.onclick = () =>
        confirmDeletion(
          "/api/jobs/" + row.job_id + "/documents/" + row.document_id,
          "Delete document",
          "This removes the original document, its annotations and downloads. Upload history remains.",
          async () => {
            selected.delete(row.id);
            await load();
            message.textContent = t(
              "Document content deleted. Upload history retained.",
            );
          },
          (error) => {
            message.textContent = error;
          },
          setBusy,
        );
      actions.append(link, document.createTextNode(" "), remove);
    } else {
      actions.textContent = "—";
    }
    tr.append(actions);
    tbody.append(tr);
  }
  updateSelection();
  document.querySelector("#documents-previous").disabled = offset === 0 || busy;
  document.querySelector("#documents-next").disabled =
    offset + 50 >= total || busy;
  document.querySelector("#documents-page").textContent =
    `${number(Math.min(total, offset + 1))}–${number(Math.min(total, offset + 50))} / ${number(total)}`;
}
function updateSelection() {
  const eligible = records.filter((row) => row.state === "STORED");
  const checked = eligible.filter((row) => selected.has(row.id)).length;
  selectVisible.checked = eligible.length > 0 && checked === eligible.length;
  selectVisible.indeterminate = checked > 0 && checked < eligible.length;
  selectVisible.disabled = busy || !eligible.length;
  deleteSelected.hidden = selected.size === 0;
  deleteSelected.disabled = busy || selected.size === 0;
  selectionCount.textContent = selected.size
    ? t("{count} selected", { count: number(selected.size) })
    : "";
  document.querySelector("#delete-all-documents").disabled = busy;
  document.querySelector("#refresh-documents").disabled = busy;
  filter.disabled = busy;
}
function setBusy(value) {
  busy = value;
  render();
}
selectVisible.onchange = () => {
  for (const row of records.filter((row) => row.state === "STORED")) {
    selectVisible.checked
      ? selected.set(row.id, {
          job_id: row.job_id,
          document_id: row.document_id,
        })
      : selected.delete(row.id);
    const checkbox = tbody.querySelector(`[data-select-document="${row.id}"]`);
    if (checkbox) checkbox.checked = selected.has(row.id);
  }
  updateSelection();
};
deleteSelected.onclick = () => {
  const documents = [...selected.values()];
  if (!documents.length || busy) return;
  confirmDeletion(
    "/api/my/documents/delete",
    t("Delete selected documents ({count})", {
      count: number(documents.length),
    }),
    "This deletes only the selected documents and their annotations and frees your quota. Upload history remains.",
    async () => {
      selected.clear();
      await load();
      message.textContent = t(
        "Document content deleted. Upload history retained.",
      );
    },
    (error) => {
      message.textContent = error;
    },
    setBusy,
    documents,
  );
};

async function load() {
  const [history, usage] = await Promise.all([
    fetch(
      base +
        `/api/my/documents?${new URLSearchParams({ offset, limit: 50, ...(filter.value !== "all" ? { state: filter.value } : {}), ...(job ? { job_id: job } : {}) })}`,
      {
        cache: "no-store",
      },
    ),
    fetch(base + "/api/my/document-usage", { cache: "no-store" }),
  ]);
  if (history.status === 401 || usage.status === 401) {
    window.dispatchEvent(new Event("temu-session-expired"));
    return;
  }
  if (!history.ok || !usage.ok)
    throw new Error(
      t("The service is temporarily unavailable. Please try again later."),
    );
  const data = await history.json();
  records = data.items;
  total = data.total;
  if (offset > 0 && offset >= total) {
    offset = Math.floor(Math.max(0, total - 1) / 50) * 50;
    return load();
  }
  paintQuota(await usage.json());
  render();
}
document.querySelector("#documents-previous").onclick = () => {
  offset = Math.max(0, offset - 50);
  load().catch((error) => (message.textContent = error.message));
};
document.querySelector("#documents-next").onclick = () => {
  offset += 50;
  load().catch((error) => (message.textContent = error.message));
};
document.querySelector("#refresh-documents").onclick = () =>
  load().catch((error) => (message.textContent = error.message));
filter.onchange = () => {
  selected.clear();
  offset = 0;
  load().catch((error) => (message.textContent = error.message));
};
onLocaleChange(render);
load().catch((error) => (message.textContent = error.message));

document.querySelector("#delete-all-documents").onclick = () =>
  confirmDeletion(
    job ? "/api/jobs/" + encodeURIComponent(job) : "/api/my/documents",
    "Delete all documents",
    job
      ? "This deletes all documents, annotations and downloads in this project and frees your quota. Upload history remains."
      : "This deletes all retained documents and annotations across your projects and frees your quota. Upload history remains.",
    async () => {
      selected.clear();
      offset = 0;
      await load();
      message.textContent = t(
        "Document content deleted. Upload history retained.",
      );
    },
    (error) => {
      message.textContent = error;
    },
    setBusy,
  );
