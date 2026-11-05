import { showDialog } from "./progress.js";
const base = document.querySelector("meta[name=app-prefix]").content;
/* UI messages are centralized here; templates contain the English page copy. */
const messages = {
  noModels:
    "No validated models are available for this language. Inference is currently unavailable.",
  choose: "Expand a category and choose one or more checkpoints.",
  unavailable: "Not available for this language",
  loadingError:
    "The model catalog could not be loaded. Please reload this page.",
  uploadError: "The request could not be submitted. Please try again.",
};
const form = document.querySelector("#request-form");
const language = document.querySelector("#language");
const entities = document.querySelector("#entities");
const files = document.querySelector("#files");
const button = document.querySelector("#submit");
const error = document.querySelector("#error");
let catalog = [],
  busy = false;
function selected() {
  return [
    ...new Set(
      [...entities.querySelectorAll("input:checked")].map((x) => x.value),
    ),
  ];
}
function selectedCategories() {
  const active = new Set(selected());
  return [
    ...new Set(
      catalog
        .filter((row) => active.has(row.model_id || row.entity))
        .map((row) => row.display_name),
    ),
  ];
}
function update() {
  for (const detail of entities.querySelectorAll("details[data-category]")) {
    const active = new Set(selected());
    const ids = new Set(
      catalog
        .filter(
          (row) =>
            row.entity === detail.dataset.category &&
            active.has(row.model_id || row.entity),
        )
        .map((row) => row.model_id || row.entity),
    );
    detail.querySelector(".model-count").textContent = `${ids.size} active`;
  }
  const pasted = document.querySelector("#input-mode").value === "PASTED_TEXT";
  const value = document.querySelector("#pasted-text").value;
  document.querySelector("#paste-counter").textContent =
    `${Array.from(value).length} characters · ${new TextEncoder().encode(value).length} UTF-8 bytes`;
  button.disabled =
    busy ||
    !selected().length ||
    (pasted ? !value.trim() : !files.files.length);
  if (pasted) {
    document.querySelector("#summary").textContent =
      `${document.querySelector("#document-name").value || "pasted-text.txt"} · ${new TextEncoder().encode(value).length} bytes · ${language.value} · ${selectedCategories().join(", ")} · ${selected().length} model(s)`;
    return;
  }
  const names = [...files.files].map((x) => x.name);
  const bytes = [...files.files].reduce((sum, x) => sum + x.size, 0);
  const isZip = names.length === 1 && names[0].toLowerCase().endsWith(".zip");
  document.querySelector("#summary").textContent = names.length
    ? `${names.join(", ")}\n${(bytes / 1024 / 1024).toFixed(2)} MB · ${isZip ? "ZIP document count is checked by the server" : names.length + " document(s)"}\nLanguage: ${language.selectedOptions[0]?.textContent || ""} · Entities: ${selectedCategories().join(", ") || "None"} · ${selected().length} model(s)`
    : "No documents selected.";
}
function modelChoice(row, retained, categories = []) {
  const label = document.createElement("label");
  const supported = !row.languages || row.languages.includes(language.value);
  const available = row.available && supported;
  label.className = `entity${available ? "" : " unavailable"}`;
  const check = document.createElement("input");
  check.type = "checkbox";
  check.name = "models";
  check.value = row.model_id || row.entity;
  check.disabled = !available;
  check.checked = available && retained.has(check.value);
  const copy = document.createElement("span");
  copy.textContent = row.model_name || row.model_id || row.display_name;
  const detail = document.createElement("small");
  detail.textContent = available
    ? row.description || categories.join(", ") || row.display_name
    : !supported
      ? "Not validated for this document language."
      : row.unavailable_reason || messages.unavailable;
  copy.append(detail);
  if (categories.length) {
    const categoryList = document.createElement("small");
    categoryList.textContent = categories.join(" · ");
    copy.append(categoryList);
  }
  label.append(check, copy);
  const container = document.createElement("div");
  container.className = "model-choice";
  container.append(label);
  if (row.model_id) {
    const info = document.createElement("details");
    info.className = "model-information";
    const summary = document.createElement("summary");
    summary.textContent = "Model information";
    const content = document.createElement("p");
    content.textContent = `${row.model_id}${row.version ? " · version " + row.version : ""}${row.languages ? " · Languages: " + row.languages.join(", ") : ""}`;
    info.append(summary, content);
    if (
      row.repository &&
      /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(row.repository)
    ) {
      const link = document.createElement("a");
      link.href = "https://huggingface.co/" + row.repository;
      link.textContent = row.repository;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      info.append(link);
    }
    const metrics = document.createElement("p");
    metrics.textContent = Object.keys(row.metrics || {}).length
      ? "Verified metrics: " + JSON.stringify(row.metrics)
      : "No independently verified metrics registered.";
    info.append(metrics);
    container.append(info);
  }
  return container;
}
function render() {
  // A language change may retain compatible multilingual choices, never create selections.
  const retained = new Set(selected());
  entities.replaceChildren();
  const rows = catalog.filter((row) => row.language === language.value);
  const multilingual = catalog.filter((row) => row.language === "mul");
  const categories = new Map();
  for (const row of [...rows, ...multilingual]) {
    if (!categories.has(row.entity))
      categories.set(row.entity, row.display_name);
  }
  const local = document.createElement("div");
  local.className = "category-list";
  for (const [key, name] of categories) {
    const category = document.createElement("details");
    category.dataset.category = key;
    category.className = "model-category";
    const heading = document.createElement("summary");
    heading.textContent = name;
    const count = document.createElement("span");
    count.className = "model-count";
    heading.append(count);
    category.append(heading);
    const choices = rows.filter((row) => row.entity === key);
    for (const row of choices) category.append(modelChoice(row, retained));
    if (!choices.length) {
      const hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent =
        "See Multilingual models below for registered checkpoints.";
      category.append(hint);
    }
    local.append(category);
  }
  entities.append(local);
  const global = document.createElement("section");
  global.id = "multilingual-models";
  const title = document.createElement("h3");
  title.textContent = "Multilingual models";
  global.append(title);
  const unique = new Map();
  for (const row of multilingual) {
    if (!row.model_id) continue;
    if (!unique.has(row.model_id))
      unique.set(row.model_id, { row, categories: [] });
    unique.get(row.model_id).categories.push(row.display_name);
  }
  for (const { row, categories } of unique.values())
    global.append(modelChoice(row, retained, categories));
  if (!unique.size) {
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = "No multilingual checkpoints registered.";
    global.append(hint);
  }
  entities.append(global);
  document.querySelector("#catalog-message").textContent = [
    ...rows,
    ...multilingual,
  ].some(
    (row) =>
      row.available &&
      (!row.languages || row.languages.includes(language.value)),
  )
    ? messages.choose
    : messages.noModels;
  update();
}
language.addEventListener("change", render);
entities.addEventListener("change", (event) => {
  if (event.target.matches("input[type=checkbox]"))
    for (const check of entities.querySelectorAll("input[type=checkbox]"))
      if (check.value === event.target.value && !check.disabled)
        check.checked = event.target.checked;
  update();
});
files.addEventListener("change", update);
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || !selected().length || !form.reportValidity()) return;
  busy = true;
  error.hidden = true;
  update();
  button.textContent = "Submitting…";
  try {
    const body = new FormData(form);
    body.delete("models");
    for (const identity of selected()) body.append("models", identity);
    if (document.querySelector("#input-mode").value === "PASTED_TEXT") {
      body.delete("pasted_text");
      body.append(
        "pasted_text_file",
        new Blob([document.querySelector("#pasted-text").value], {
          type: "text/plain",
        }),
        "pasted-text.txt",
      );
    }
    const data = await new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", base + "/api/jobs");
      request.responseType = "json";
      document.querySelector("#upload-state").hidden = false;
      request.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          document.querySelector("#upload-progress").value =
            (event.loaded / event.total) * 100;
          document.querySelector("#upload-message").textContent =
            `Uploading: ${event.loaded} / ${event.total} bytes`;
        }
      };
      request.upload.onload = () => {
        document.querySelector("#upload-message").textContent =
          "Upload complete. Validating and registering your request…";
      };
      request.onload = () => {
        if (request.status === 202) resolve(request.response);
        else
          reject(new Error(request.response?.detail || messages.uploadError));
      };
      request.onerror = () => reject(new Error(messages.uploadError));
      request.send(body);
    });
    const accepted = showDialog(
      "Request accepted",
      "Your documents have entered the persistent queue. Save your private link.",
      [
        {
          label: "Copy private link",
          run: () => navigator.clipboard.writeText(data.url),
        },
        { label: "Continue to request", run: () => location.assign(data.url) },
      ],
    );
    const link = document.createElement("a");
    link.href = data.url;
    link.textContent = data.url;
    link.className = "private-link";
    accepted.append(link);
    accepted.addEventListener("close", () => location.assign(data.url));
  } catch (exc) {
    error.textContent = exc.message || messages.uploadError;
    error.hidden = false;
    busy = false;
    button.textContent = "Start annotation →";
    update();
  }
});
(async () => {
  try {
    const responses = await Promise.all([
      fetch(base + "/api/languages"),
      fetch(base + "/api/models"),
    ]);
    if (responses.some((x) => !x.ok)) throw new Error();
    const [languages, models] = await Promise.all(
      responses.map((x) => x.json()),
    );
    catalog = models;
    language.replaceChildren();
    for (const row of languages) {
      const option = document.createElement("option");
      option.value = row.code;
      option.textContent = row.display_name;
      language.append(option);
    }
    render();
  } catch (_) {
    document.querySelector("#catalog-message").textContent =
      messages.loadingError;
  }
})();

const dropZone = document.querySelector("#drop-zone");
for (const event of ["dragover", "dragenter"])
  dropZone.addEventListener(event, (e) => {
    e.preventDefault();
    dropZone.classList.add("dragging");
  });
dropZone.addEventListener("dragleave", () =>
  dropZone.classList.remove("dragging"),
);
dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
  files.files = event.dataTransfer.files;
  update();
});

for (const tab of document.querySelectorAll("[data-mode]")) {
  tab.addEventListener("click", () => {
    const mode = tab.dataset.mode,
      pasted = mode === "PASTED_TEXT";
    document.querySelector("#input-mode").value = mode;
    document
      .querySelectorAll("[data-mode]")
      .forEach((x) => x.setAttribute("aria-selected", String(x === tab)));
    document.querySelector("#paste-panel").hidden = !pasted;
    document.querySelector("#file-panel").hidden = pasted;
    document.querySelector("#pasted-text").disabled = !pasted;
    document.querySelector("#pasted-text").required = pasted;
    document.querySelector("#document-name").disabled = !pasted;
    files.disabled = pasted;
    files.required = !pasted;
    document
      .querySelector("#file-panel")
      .setAttribute("aria-labelledby", tab.id);
    document
      .querySelectorAll("[data-mode]")
      .forEach((x) => (x.tabIndex = x === tab ? 0 : -1));
    document.querySelector("#upload-hint").textContent =
      mode === "ZIP_ENTRY"
        ? "One ZIP archive · nested TXT folders supported"
        : "UTF-8 TXT · multiple files supported";
    files.accept = mode === "ZIP_ENTRY" ? ".zip" : ".txt";
    files.multiple = mode !== "ZIP_ENTRY";
    files.value = "";
    renderFiles();
    update();
  });
  tab.addEventListener("keydown", (event) => {
    if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      const tabs = [...document.querySelectorAll("[data-mode]")];
      const index =
        (tabs.indexOf(tab) +
          (event.key === "ArrowRight" ? 1 : -1) +
          tabs.length) %
        tabs.length;
      tabs[index].focus();
      tabs[index].click();
    }
  });
}
function renderFiles() {
  const list = document.querySelector("#file-list");
  list.replaceChildren();
  [...files.files].forEach((file, index) => {
    const row = document.createElement("div"),
      name = document.createElement("span"),
      remove = document.createElement("button");
    name.textContent = file.name;
    remove.type = "button";
    remove.className = "secondary";
    remove.textContent = "Remove";
    remove.setAttribute("aria-label", "Remove " + file.name);
    remove.onclick = () => {
      const transfer = new DataTransfer();
      [...files.files]
        .filter((_, i) => i !== index)
        .forEach((f) => transfer.items.add(f));
      files.files = transfer.files;
      renderFiles();
      update();
    };
    row.append(name, remove);
    list.append(row);
  });
}
files.addEventListener("change", renderFiles);
dropZone.addEventListener("drop", renderFiles);
document.querySelector("#pasted-text").addEventListener("input", update);
document.querySelector("#document-name").addEventListener("input", update);
document.querySelector("#clear-text").onclick = () => {
  document.querySelector("#pasted-text").value = "";
  update();
};
document.querySelector("#copy-text").onclick = () =>
  navigator.clipboard.writeText(document.querySelector("#pasted-text").value);
