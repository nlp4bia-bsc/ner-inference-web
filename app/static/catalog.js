import { t, number, onLocaleChange } from "./auth.js";
export function mountCatalog({ onChange = () => {}, readonly = false } = {}) {
  const base = document.querySelector("meta[name=app-prefix]").content;
  const language = document.querySelector("#language"),
    entities = document.querySelector("#entities");
  let catalog = [],
    languages = [];
  const messages = {
    get noModels() {
      return t("No configured models are available for this language.");
    },
    get choose() {
      return t("Expand a category and choose one or more checkpoints.");
    },
    get unavailable() {
      return t("Not available for this language");
    },
    get loadingError() {
      return t(
        "The model catalog could not be loaded. Please reload this page.",
      );
    },
  };
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
          .map((row) => t(row.display_name)),
      ),
    ];
  }
  function modelChoice(row, retained, categories = []) {
    const label = document.createElement("label");
    const supported = supports(row);
    const available = row.available && supported;
    label.className = `entity${available ? "" : " unavailable"}`;
    const check = document.createElement("input");
    check.type = "checkbox";
    check.name = "models";
    check.value = row.model_id || row.entity;
    check.disabled = readonly || !available;
    check.checked = available && retained.has(check.value);
    const copy = document.createElement("span");
    copy.textContent = row.model_name || row.model_id || row.display_name;
    const detail = document.createElement("small");
    detail.textContent = available
      ? t(row.description || "") ||
        categories.map((value) => t(value)).join(", ") ||
        t(row.display_name)
      : !supported
        ? t("Not validated for this document language.")
        : t(row.unavailable_reason || "") || messages.unavailable;
    const availability = document.createElement("small");
    availability.className = "model-availability";
    availability.textContent = t(
      available
        ? row.load_state === "cached" || row.load_state === "local"
          ? "Cached · ready to load"
          : row.load_state === "on_demand"
            ? "Download on first use"
            : "Available"
        : "Unavailable",
    );
    copy.append(availability, detail);
    if (categories.length) {
      const categoryList = document.createElement("small");
      categoryList.textContent = categories
        .map((value) => t(value))
        .join(" · ");
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
      summary.textContent = t("Model information");
      const content = document.createElement("p");
      content.textContent = `${row.model_id}${row.version ? " · " + t("Version") + " " + row.version : ""}${row.languages ? " · " + t("Language") + ": " + row.languages.join(", ") : ""}`;
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
        ? t("Verified metrics") + ": " + JSON.stringify(row.metrics)
        : t("No independently verified metrics registered.");
      info.append(metrics);
      container.append(info);
    }
    return container;
  }
  function supports(row) {
    return language.value === "oth"
      ? row.allows_other === true
      : !row.languages || row.languages.includes(language.value);
  }
  function render() {
    // A language change may retain compatible multilingual choices, never create selections.
    const retained = new Set(selected());
    const multilingualOpen =
      entities.querySelector("#multilingual-models")?.open ?? false;
    const expanded = new Set(
      [...entities.querySelectorAll("details[data-category][open]")].map(
        (node) => node.dataset.category,
      ),
    );
    for (const option of language.options) {
      const row = languages.find((row) => row.code === option.value);
      if (row) option.textContent = t(row.display_name);
    }
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
      category.open = expanded.has(key);
      const heading = document.createElement("summary");
      const caption = document.createElement("span");
      caption.textContent = t(name);
      heading.append(caption);
      const count = document.createElement("span");
      count.className = "model-count";
      heading.append(count);
      category.append(heading);
      const choices = rows.filter((row) => row.entity === key);
      for (const row of choices) category.append(modelChoice(row, retained));
      if (!choices.length) {
        const hint = document.createElement("p");
        hint.className = "hint";
        hint.textContent = t(
          "See Multilingual models below for registered checkpoints.",
        );
        category.append(hint);
      }
      local.append(category);
    }
    entities.append(local);
    const global = document.createElement("details");
    global.open = multilingualOpen;
    if (language.value === "oth") global.open = true;
    global.id = "multilingual-models";
    const title = document.createElement("summary");
    title.textContent = t("Multilingual models");
    global.append(title);
    const explanation = document.createElement("p");
    explanation.className = "hint";
    explanation.textContent = t(
      language.value === "oth"
        ? "For Other, only multilingual models are available; the specified language is recorded but not used yet."
        : "Multilingual checkpoints are validated per document language. Check availability before submitting.",
    );
    global.append(explanation);
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
      hint.textContent = t("No multilingual checkpoints registered.");
      global.append(hint);
    }
    entities.append(global);
    document.querySelector("#catalog-message").textContent = [
      ...rows,
      ...multilingual,
    ].some((row) => row.available && supports(row))
      ? messages.choose
      : messages.noModels;
    onChange();
  }
  language.addEventListener("change", render);
  entities.addEventListener("change", (event) => {
    if (event.target.matches("input[type=checkbox]"))
      for (const check of entities.querySelectorAll("input[type=checkbox]"))
        if (check.value === event.target.value && !check.disabled)
          check.checked = event.target.checked;
    onChange();
  });
  const loading = document.createElement("div");
  loading.className = "category-list";
  loading.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 6; i++) {
    const placeholder = document.createElement("div");
    placeholder.className = "skeleton";
    loading.append(placeholder);
  }
  entities.append(loading);
  (async () => {
    try {
      const responses = await Promise.all([
        fetch(base + "/api/languages"),
        fetch(base + "/api/models"),
      ]);
      if (responses.some((x) => !x.ok)) throw new Error();
      const [loadedLanguages, models] = await Promise.all(
        responses.map((x) => x.json()),
      );
      catalog = models;
      languages = loadedLanguages;
      language.replaceChildren();
      for (const row of languages) {
        const option = document.createElement("option");
        option.value = row.code;
        option.textContent = t(row.display_name);
        language.append(option);
      }
      render();
    } catch (_) {
      document.querySelector("#catalog-message").textContent =
        messages.loadingError;
    }
  })();

  onLocaleChange(render);
  return {
    selected,
    selectedCategories,
    get rows() {
      return catalog;
    },
  };
}
