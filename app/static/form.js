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
  button.disabled = busy || !selected().length || !files.files.length;
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
    const response = await fetch(base + "/api/jobs", {
      method: "POST",
      body: new FormData(form),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string" ? data.detail : messages.uploadError,
      );
    location.assign(data.url);
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
