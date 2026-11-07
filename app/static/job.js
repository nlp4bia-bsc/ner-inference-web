import { startProgress } from "./progress.js";
import { t, date, number, onLocaleChange, localized } from "./auth.js";
const base = document.querySelector("meta[name=app-prefix]").content;
const token = location.pathname.split("/").pop(),
  endpoint = base + "/api/jobs/" + token;
const $ = (id) => document.getElementById(id);
let expired = false,
  latestProgress = null,
  latestData = null;
const titles = {
  QUEUED: "Your request is queued.",
  PROCESSING: "Your documents are being processed.",
  COMPLETED: "Your annotations are ready.",
  COMPLETED_WITH_ERRORS: "Your partial results are ready.",
  FAILED: "Processing failed.",
};
async function render(progress) {
  if (expired) return;
  const sameState =
    latestProgress &&
    [
      "status",
      "annotated_documents",
      "failed_documents",
      "total_documents",
      "expires_at",
    ].every((key) => latestProgress[key] === progress[key]);
  latestProgress = progress;
  if (latestData && sameState) {
    paint(latestData, progress);
    return;
  }
  const response = await fetch(endpoint, { cache: "no-store" });
  if (response.status === 401)
    window.dispatchEvent(new Event("temu-session-expired"));
  if (response.status === 410) return expire();
  if (!response.ok) throw new Error("Status unavailable");
  const data = await response.json();
  latestData = data;
  paint(data, progress);
}
function paint(data, progress) {
  data = {
    ...data,
    status: progress.status,
    queue_position: progress.queue_position,
    document_count: progress.total_documents,
  };

  $("heading").textContent = t(titles[data.status] || data.status);
  $("state").textContent = t(data.status);
  $("details").replaceChildren();
  for (const [name, value] of [
    [t("Request ID"), data.job_id],
    [t("Submitted"), date(data.created_at)],
    [t("Language"), data.language],
    [t("Documents"), data.document_count],
    [t("Entity types"), data.entities.join(", ")],
    [t("Queue position"), data.queue_position ?? "—"],
  ]) {
    const dt = document.createElement("dt"),
      dd = document.createElement("dd");
    dt.textContent = name;
    dd.textContent = typeof value === "number" ? number(value) : value;
    $("details").append(dt, dd);
  }
  $("status-message").textContent =
    data.error_summary ||
    (data.status === "COMPLETED_WITH_ERRORS"
      ? t(
          "Some documents failed. Downloads contain only validated annotated documents and an explicit partial manifest.",
        )
      : "");
  const available = progress.annotated_documents > 0;
  $("downloads").hidden = !available;
  $("explore").href = localized(base + "/jobs/" + token + "/viewer");
  $("brat").hidden = !data.downloads_available;
  $("tsv").hidden = !data.downloads_available;
  $("statistics").hidden = !data.downloads_available;
  $("brat").href = endpoint + "/download/brat";
  $("tsv").href = endpoint + "/download/tsv";
  $("statistics").href = endpoint + "/statistics";
  if (data.summary) {
    $("summary").hidden = false;
    $("summary").replaceChildren();
    for (const [label, key] of [
      [t("Documents"), "documents"],
      [t("Entities"), "annotations"],
      [t("Words"), "words"],
      [t("Tokens"), "tokens"],
      [t("Sentences"), "sentences"],
    ]) {
      const card = document.createElement("div"),
        number = document.createElement("strong"),
        name = document.createElement("span");
      number.textContent = data.summary[key] ?? "—";
      name.textContent = label;
      card.append(number, name);
      $("summary").append(card);
    }
  }
}
function expire() {
  expired = true;
  $("heading").textContent = t("Results have expired.");
  $("state").textContent = t("EXPIRED");
  $("downloads").hidden = true;
  $("summary").replaceChildren();
  $("summary").hidden = true;
  $("details").replaceChildren();
}
const copy = document.createElement("button");
copy.className = "secondary";
copy.textContent = t("Copy private link");
copy.dataset.i18n = "Copy private link";
copy.onclick = async () => {
  try {
    await navigator.clipboard.writeText(location.href);
  } catch (_) {
    $("status-message").textContent = t("The link could not be copied.");
  }
};
$("details").after(copy);
startProgress(endpoint, { onChange: render, onExpire: expire });

onLocaleChange(() => {
  if (expired) expire();
  else if (latestData) paint(latestData, latestProgress);
});
