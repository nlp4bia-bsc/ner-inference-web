import { showDialog } from "./progress.js";
import { t, number, onLocaleChange, localized } from "./auth.js";
import { mountCatalog } from "./catalog.js";
const base = document.querySelector("meta[name=app-prefix]").content;
const form = document.querySelector("#request-form");
const language = document.querySelector("#language");
const entities = document.querySelector("#entities");
const files = document.querySelector("#files");
const jobName = document.querySelector("#job-name");
const otherLanguage = document.querySelector("#other-language");
const button = document.querySelector("#submit");
const error = document.querySelector("#error");
let busy = false;
let remaining = null;
window.addEventListener("document-quota", (event) => {
  remaining = event.detail.remaining;
  update();
});
const catalog = mountCatalog({ onChange: update });
const normalize = document.querySelector("#normalize"),
  lexicalMethod = document.querySelector("#normalization-lexical-method"),
  useBiEncoder = document.querySelector("#use-bi-encoder"),
  normalizationMethod = document.querySelector("#normalization-method"),
  normalizationThreshold = document.querySelector("#normalization-threshold");
function normalizationOptions() {
  const enabled = normalize.checked,
    bi = enabled && useBiEncoder.checked;
  document.querySelector("#normalization-options").hidden = !enabled;
  normalizationMethod.value = bi ? "bi_encoder" : lexicalMethod.value;
  normalizationMethod.disabled = !enabled;
  lexicalMethod.disabled = !enabled || bi;
  useBiEncoder.disabled = !enabled;
  normalizationThreshold.disabled =
    !enabled || bi || lexicalMethod.value === "exact";
  document.querySelector("#normalization-threshold-field").hidden =
    normalizationThreshold.disabled;
  document.querySelector("#bi-encoder-warning").hidden = !bi;
}
for (const control of [
  normalize,
  lexicalMethod,
  useBiEncoder,
  normalizationThreshold,
])
  control.addEventListener("change", () => {
    normalizationOptions();
    update();
  });
normalizationOptions();
function normalizationSummary() {
  return normalize.checked
    ? "\n" +
        t("Concept normalization") +
        ": " +
        t(
          {
            exact: "Exact string matching",
            levenshtein: "Fuzzy match",
            bi_encoder: "Bi-encoder",
          }[normalizationMethod.value],
        ) +
        (normalizationMethod.value === "levenshtein"
          ? " · " +
            t("Similarity threshold") +
            ": " +
            normalizationThreshold.value
          : "")
    : "";
}
function selected() {
  return catalog.selected();
}
function selectedCategories() {
  return catalog.selectedCategories();
}
function update() {
  const other = language.value === "oth";
  document.querySelector("#other-language-field").hidden = !other;
  otherLanguage.disabled = !other;
  otherLanguage.required = other;
  for (const detail of entities.querySelectorAll("details[data-category]")) {
    const active = new Set(selected());
    const ids = new Set(
      catalog.rows
        .filter(
          (row) =>
            row.entity === detail.dataset.category &&
            active.has(row.model_id || row.entity),
        )
        .map((row) => row.model_id || row.entity),
    );
    detail.querySelector(".model-count").textContent = t("{count} active", {
      count: number(ids.size),
    });
  }
  const pasted = document.querySelector("#input-mode").value === "PASTED_TEXT";
  const value = document.querySelector("#pasted-text").value;
  document.querySelector("#paste-counter").textContent = t(
    "{count} characters · {bytes} UTF-8 bytes",
    {
      count: number(Array.from(value).length),
      bytes: number(new TextEncoder().encode(value).length),
    },
  );
  button.disabled =
    busy ||
    remaining === 0 ||
    (other && !otherLanguage.value.trim()) ||
    !selected().length ||
    (pasted ? !value.trim() : !files.files.length);
  if (pasted) {
    document.querySelector("#summary").textContent =
      (jobName.value.trim() ? jobName.value.trim() + "\n" : "") +
      `${document.querySelector("#document-name").value || "pasted-text.txt"} · ${number(new TextEncoder().encode(value).length)} bytes · ${other ? "OTH · " + otherLanguage.value : language.value} · ${selectedCategories().join(", ")} · ${t("{count} model(s)", { count: number(selected().length) })}` +
      normalizationSummary();
    return;
  }
  const names = [...files.files].map((x) => x.name);
  const bytes = [...files.files].reduce((sum, x) => sum + x.size, 0);
  const isZip = names.length === 1 && names[0].toLowerCase().endsWith(".zip");
  document.querySelector("#summary").textContent = names.length
    ? `${names.join(", ")}\n${(bytes / 1024 / 1024).toFixed(2)} MB · ${isZip ? t("ZIP document count is checked by the server") : t("{count} document(s)", { count: number(names.length) })}\n${t("Language")}: ${language.selectedOptions[0]?.textContent || ""} · ${t("Entities")}: ${selectedCategories().join(", ") || t("None")} · ${t("{count} model(s)", { count: number(selected().length) })}`
    : t("No documents selected.");
  document.querySelector("#summary").textContent += normalizationSummary();
  if (jobName.value.trim())
    document.querySelector("#summary").prepend(jobName.value.trim() + "\n");
}
function uploadChanged() {
  if (!jobName.value.trim() && files.files.length)
    jobName.value = files.files[0].name.replace(/\.[^.]+$/, "").slice(0, 200);
  update();
}
files.addEventListener("change", uploadChanged);
jobName.addEventListener("input", update);
otherLanguage.addEventListener("input", update);
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || !selected().length || !form.reportValidity()) return;
  busy = true;
  error.hidden = true;
  document.querySelector("#upload-state").hidden = true;
  document.querySelector("#upload-progress").value = 0;
  document.querySelector("#upload-message").textContent = "";
  update();
  button.textContent = t("Submitting…");
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
    const identityResponse = await fetch(base + "/api/auth/session");
    if (!identityResponse.ok) {
      location.assign(base + "/login");
      return;
    }
    const identity = await identityResponse.json();
    const data = await new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", base + "/api/jobs");
      request.responseType = "json";
      request.setRequestHeader("X-CSRF-Token", identity.csrf_token);
      document.querySelector("#upload-state").hidden = false;
      request.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          document.querySelector("#upload-progress").value =
            (event.loaded / event.total) * 100;
          document.querySelector("#upload-message").textContent = t(
            "Uploading: {loaded} / {total} bytes",
            { loaded: number(event.loaded), total: number(event.total) },
          );
        }
      };
      request.upload.onload = () => {
        document.querySelector("#upload-message").textContent = t(
          "Upload complete. Validating and registering your request…",
        );
      };
      request.onload = () => {
        if (request.status === 202) resolve(request.response);
        else
          reject(
            new Error(
              t(request.response?.detail) ||
                t("The request could not be submitted. Please try again."),
            ),
          );
      };
      request.onerror = () =>
        reject(
          new Error(t("The request could not be submitted. Please try again.")),
        );
      request.send(body);
    });
    const accepted = showDialog(
      t("Request accepted"),
      t(
        "Your documents are queued. You and authorized administrators can access this job.",
      ),
      [
        {
          label: t("Copy private link"),
          run: () => navigator.clipboard.writeText(localized(data.url)),
        },
        {
          label: t("Continue to request"),
          run: () => location.assign(localized(data.url)),
        },
      ],
    );
    const link = document.createElement("a");
    link.href = localized(data.url);
    link.textContent = localized(data.url);
    link.className = "private-link";
    accepted.append(link);
    accepted.addEventListener("close", () =>
      location.assign(localized(data.url)),
    );
  } catch (exc) {
    document.querySelector("#upload-state").hidden = true;
    document.querySelector("#upload-progress").value = 0;
    document.querySelector("#upload-message").textContent = "";
    error.textContent =
      exc.message || t("The request could not be submitted. Please try again.");
    error.hidden = false;
    busy = false;
    button.textContent = t("Start annotation") + " →";
    update();
  }
});
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
  uploadChanged();
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
        ? t("One ZIP archive · nested TXT folders supported")
        : t("UTF-8 TXT · multiple files supported");
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
    remove.textContent = t("Remove");
    remove.setAttribute("aria-label", t("Remove") + " " + file.name);
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

onLocaleChange(() => {
  renderFiles();
  update();
  document.querySelector("#upload-hint").textContent = t(
    document.querySelector("#input-mode").value === "ZIP_ENTRY"
      ? "One ZIP archive · nested TXT folders supported"
      : "UTF-8 TXT · multiple files supported",
  );
});
