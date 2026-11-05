const language = document.querySelector("#auth-locale");
if (language)
  language.onchange = () => {
    const url = new URL(location.href);
    url.searchParams.set("lang", language.value);
    location.assign(url.pathname + url.search);
  };
const profession = document.querySelector("#professional_role");
function toggleOther() {
  const other = profession.value === "OTHER";
  document.querySelector("#professional-other").hidden = !other;
  document.querySelector("#professional_role_other").required = other;
}
if (profession) {
  profession.onchange = toggleOther;
  toggleOther();
}
if (document.querySelector("#recovery-codes")) {
  window.addEventListener("pagehide", () => document.body.replaceChildren());
}

// Credential-free, same-origin notification; receivers validate with the server.
if (typeof BroadcastChannel === "function") {
  const base = document.querySelector('meta[name="app-prefix"]').content;
  const channel = new BroadcastChannel("temu-session:" + base);
  channel.postMessage("check");
  channel.close();
}
