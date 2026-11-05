import { showDialog } from "./progress.js";
const base = document.querySelector("meta[name=app-prefix]").content;
/* UI messages are centralized here; templates contain the English page copy. */
const messages = {
  noModels:
    "No validated models are available for this language. Inference is currently unavailable.",
  choose: "Choose one or more available entity types.",
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
  return [...entities.querySelectorAll("input:checked")].map((x) => x.value);
}
function update() {
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
      `${document.querySelector("#document-name").value || "pasted-text.txt"} · ${new TextEncoder().encode(value).length} bytes · ${language.value} · ${selected().join(", ")}`;
    return;
  }
  const names = [...files.files].map((x) => x.name);
  const bytes = [...files.files].reduce((sum, x) => sum + x.size, 0);
  const isZip = names.length === 1 && names[0].toLowerCase().endsWith(".zip");
  document.querySelector("#summary").textContent = names.length
    ? `${names.join(", ")}\n${(bytes / 1024 / 1024).toFixed(2)} MB · ${isZip ? "ZIP document count is checked by the server" : names.length + " document(s)"}\nLanguage: ${language.selectedOptions[0]?.textContent || ""} · Entities: ${selected().join(", ") || "None"}`
    : "No documents selected.";
}
function render() {
  entities.replaceChildren();
  const rows = catalog.filter((x) => x.language === language.value);
  for (const row of rows) {
    const label = document.createElement("label");
    label.className = `entity${row.available ? "" : " unavailable"}`;
    const check = document.createElement("input");
    check.type = "checkbox";
    check.name = "entities";
    check.value = row.entity;
    check.disabled = !row.available;
    check.checked = row.available;
    const copy = document.createElement("span");
    copy.textContent = row.display_name;
    const detail = document.createElement("small");
    detail.textContent = row.available
      ? row.description || row.entity
      : messages.unavailable;
    copy.append(detail);
    label.append(check, copy);
    entities.append(label);
  }
  document.querySelector("#catalog-message").textContent = rows.some(
    (x) => x.available,
  )
    ? messages.choose
    : messages.noModels;
  update();
}
language.addEventListener("change", render);
entities.addEventListener("change", update);
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
