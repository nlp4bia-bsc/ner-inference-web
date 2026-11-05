// No browser persistence: server authorization remains authoritative for every read.
const base = document.querySelector('meta[name="app-prefix"]').content;
const originalUser = document.querySelector(
  'meta[name="authenticated-user"]',
)?.content;
const channel =
  typeof BroadcastChannel === "function"
    ? new BroadcastChannel("temu-session:" + base)
    : null;
channel?.addEventListener("message", () => safelyCheck());
let announced = false;
let lost = false,
  checking = false,
  csrf = "",
  lastActivity = 0;
function clearAndLeave() {
  if (lost) return;
  lost = true;
  getSelection()?.removeAllRanges();
  document.body.replaceChildren();
  const language = ["en", "es", "ca"].includes(document.documentElement.lang)
    ? document.documentElement.lang
    : "en";
  location.replace(base + "/login?reason=expired&lang=" + language);
}
window.addEventListener("temu-session-expired", clearAndLeave);
async function check() {
  if (lost || checking) return;
  checking = true;
  try {
    const response = await fetch(base + "/api/auth/session", {
      cache: "no-store",
    });
    if (response.status === 401) return clearAndLeave();
    if (response.ok) {
      const identity = await response.json();
      if (originalUser && identity.user.id !== originalUser)
        return clearAndLeave();
      csrf = identity.csrf_token;
      if (!announced) {
        announced = true;
        channel?.postMessage("check");
      }
      document.body.hidden = false;
    }
  } finally {
    checking = false;
  }
}
async function activity() {
  if (lost || !csrf || Date.now() - lastActivity < 60000) return;
  lastActivity = Date.now();
  try {
    const response = await fetch(base + "/api/auth/touch", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: "{}",
    });
    if (response.status === 401) clearAndLeave();
  } catch {
    /* A network failure is not proof of logout. */
  }
}
const safelyCheck = () => check().catch(() => {});
window.addEventListener("pagehide", () => {
  document.body.hidden = true;
});
window.addEventListener("pageshow", safelyCheck);
window.addEventListener("focus", safelyCheck);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) safelyCheck();
});
for (const event of ["pointerdown", "keydown"])
  document.addEventListener(event, activity, { passive: true });
setInterval(safelyCheck, 15000);
safelyCheck();
