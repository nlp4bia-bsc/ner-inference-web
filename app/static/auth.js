import { messages } from "./i18n.js";
export const locales = ["en", "es", "ca"];
export function currentLocale() {
  return locales.includes(document.documentElement.lang)
    ? document.documentElement.lang
    : "en";
}
export function localized(path) {
  const url = new URL(path, location.href);
  if (url.origin === location.origin)
    url.searchParams.set("lang", currentLocale());
  return url.href;
}
export function t(key, values = {}) {
  if (typeof key !== "string") return "";
  const cap =
    typeof key === "string" &&
    key.match(/^A request may contain at most (\d+) documents\.$/);
  if (cap) {
    key = "A request may contain at most {count} documents.";
    values = { count: number(Number(cap[1])), ...values };
  }

  const value = messages[key]?.[locales.indexOf(currentLocale())] ?? key;
  return value.replace(/\{(\w+)\}/g, (match, name) =>
    String(values[name] ?? match),
  );
}
export function number(value) {
  return new Intl.NumberFormat(currentLocale()).format(value);
}
export function date(value) {
  return value
    ? new Intl.DateTimeFormat(currentLocale(), {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "—";
}
export function onLocaleChange(callback) {
  window.addEventListener("nlp4bia-locale", callback);
}
function localLinks(language) {
  for (const anchor of document.querySelectorAll("a[href]")) {
    const url = new URL(anchor.href, location.href);
    if (
      url.origin !== location.origin ||
      url.hash ||
      url.pathname.includes("/api/") ||
      url.pathname.endsWith(".json") ||
      url.pathname.includes("/static/")
    )
      continue;
    url.searchParams.set("lang", language);
    anchor.href = url.pathname + url.search;
  }
  for (const form of document.forms) {
    const url = new URL(form.action, location.href);
    if (url.origin === location.origin) {
      url.searchParams.set("lang", language);
      form.action = url.pathname + url.search;
    }
  }
  for (const input of document.querySelectorAll(
    'input[name="preferred_locale"],input[name="lang"]',
  ))
    input.value = language;
}
export function applyLocale(language = currentLocale()) {
  if (!locales.includes(language)) return;
  document.documentElement.lang = language;
  document.documentElement.dir = "ltr";
  for (const node of document.querySelectorAll("[data-i18n]"))
    node.textContent = t(node.dataset.i18n);
  for (const attr of ["placeholder", "aria-label", "data-label"])
    for (const node of document.querySelectorAll("[data-i18n-" + attr + "]"))
      node.setAttribute(attr, t(node.getAttribute("data-i18n-" + attr)));
  for (const node of document.querySelectorAll("[data-number]"))
    node.textContent = number(Number(node.dataset.number));
  for (const node of document.querySelectorAll("time[datetime]")) {
    if (!Number.isNaN(Date.parse(node.dateTime)))
      node.textContent = date(node.dateTime);
  }
  for (const node of document.querySelectorAll("[data-quota]"))
    node.textContent = t("Up to {count} documents per job", {
      count: number(Number(node.dataset.quota)),
    });
  for (const node of document.querySelectorAll("[data-request-quota]"))
    node.textContent = t(
      "Your plan allows up to {count} documents per request.",
      { count: number(Number(node.dataset.requestQuota)) },
    );
  for (const node of document.querySelectorAll("[data-label]")) {
    node.dataset.i18nDataLabel ||=
      Object.keys(messages).find((key) =>
        messages[key].includes(node.dataset.label),
      ) || node.dataset.label;
    node.dataset.label = t(node.dataset.i18nDataLabel);
  }
  const heading = document.querySelector("h1");
  if (heading) document.title = heading.textContent + " · NLP4BIA";
  for (const node of document.querySelectorAll("[data-upload-limit]"))
    node.textContent = t(
      "Maximum upload: {count} MB. Empty files and nested ZIPs are not supported.",
      { count: number(Number(node.dataset.uploadLimit)) },
    );
  for (const node of document.querySelectorAll("[data-retention-hours]"))
    node.textContent = t(
      "Results remain available for {count} hours after processing. Only your account can access them.",
      { count: number(Number(node.dataset.retentionHours)) },
    );
  localLinks(language);
}
const language = document.querySelector("#auth-locale");
if (language)
  language.onchange = () => {
    const url = new URL(location.href);
    url.searchParams.set("lang", language.value);
    history.replaceState(null, "", url.pathname + url.search);
    applyLocale(language.value);
    window.dispatchEvent(new Event("nlp4bia-locale"));
  };
const menu = document.querySelector("#menu-toggle");
if (menu)
  menu.onclick = () => {
    const open = menu.getAttribute("aria-expanded") !== "true";
    menu.setAttribute("aria-expanded", String(open));
    document.querySelector(".app-header").classList.toggle("menu-open", open);
  };
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    document
      .querySelectorAll(".account-menu[open]")
      .forEach((node) => (node.open = false));
    if (menu?.getAttribute("aria-expanded") === "true") {
      menu.click();
      menu.focus();
    }
  }
});
const profession = document.querySelector("#professional_role");
function toggleOther() {
  const other = profession.value === "OTHER";
  const caption = document.querySelector("#profession-caption");
  if (caption) {
    caption.dataset.i18n = profession.value;
    caption.textContent = t(profession.value);
  }
  document.querySelector("#professional-other").hidden = !other;
  document.querySelector("#professional_role_other").required = other;
}
if (profession) {
  profession.onchange = toggleOther;
  toggleOther();
}
for (const button of document.querySelectorAll("[data-password]"))
  button.onclick = () => {
    const field = document.getElementById(button.dataset.password),
      visible = field.type === "password";
    field.type = visible ? "text" : "password";
    button.setAttribute("aria-pressed", String(visible));
    button.querySelector("[data-i18n]").dataset.i18n = visible
      ? "Hide password"
      : "Show password";
    button.querySelector("span").textContent = t(
      visible ? "Hide password" : "Show password",
    );
  };
export function openDialog(title, message, actions = []) {
  const dialog = document.createElement("dialog");
  dialog.className = "notification-dialog";
  const heading = document.createElement("h2"),
    text = document.createElement("p");
  heading.id = "dialog-" + crypto.randomUUID();
  heading.textContent = title;
  dialog.setAttribute("aria-labelledby", heading.id);
  text.textContent = message;
  dialog.append(heading, text);
  for (const action of actions) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    button.onclick = () => action.run(dialog);
    dialog.append(button);
  }
  const close = document.createElement("button");
  close.type = "button";
  close.className = "secondary";
  close.textContent = t("Close");
  close.onclick = () => dialog.close();
  dialog.append(close);
  const focus = document.activeElement;
  dialog.addEventListener("close", () => {
    dialog.remove();
    if (focus?.isConnected) focus.focus();
  });
  document.body.append(dialog);
  dialog.showModal();
  return dialog;
}
for (const form of document.querySelectorAll("form[data-confirm]"))
  form.addEventListener("submit", (event) => {
    if (form.dataset.confirmed === "true") return;
    event.preventDefault();
    const button = event.submitter;
    const dialog = openDialog(
      t("Confirm change"),
      t("Review this administrative action before applying it."),
      [
        {
          label: t("Confirm"),
          run: () => {
            dialog.close();
            form.dataset.confirmed = "true";
            form.requestSubmit(button);
          },
        },
      ],
    );
    const detail = document.createElement("p");
    detail.className = "confirm-details";
    detail.textContent = [
      form.dataset.identity,
      ...[...form.querySelectorAll("select")].map(
        (select) =>
          `${select.closest("label")?.querySelector("[data-i18n]")?.textContent || ""}: ${select.selectedOptions[0].textContent}`,
      ),
    ]
      .filter(Boolean)
      .join("\n");
    dialog.append(detail);
  });
for (const input of document.querySelectorAll("input[data-password-min]")) {
  const validatePassword = () => {
    const length = Array.from(input.value).length;
    input.setCustomValidity(
      length &&
        (length < Number(input.dataset.passwordMin) ||
          length > Number(input.dataset.passwordMax))
        ? t("password_hint")
        : "",
    );
  };
  input.addEventListener("input", validatePassword);
  onLocaleChange(validatePassword);
}
for (const form of document.querySelectorAll(".account-form"))
  form.addEventListener("submit", () => {
    const button = form.querySelector("button[type=submit]");
    if (!button) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = t("Sending…");
  });
if (document.querySelector("#recovery-codes"))
  window.addEventListener("pagehide", () => document.body.replaceChildren());
if (
  typeof BroadcastChannel === "function" &&
  !document.querySelector('meta[name="authenticated-user"]')
) {
  const base = document.querySelector('meta[name="app-prefix"]').content;
  const channel = new BroadcastChannel("temu-session:" + base);
  channel.postMessage("check");
  channel.close();
}
applyLocale();
