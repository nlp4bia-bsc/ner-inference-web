import { startProgress } from "./progress.js";
const base = document.querySelector("meta[name=app-prefix]").content;
const token = location.pathname.split("/").pop(),
  endpoint = base + "/api/jobs/" + token;
const $ = (id) => document.getElementById(id);
let expired = false;
const titles = {
  QUEUED: "Your request is queued.",
  PROCESSING: "Your documents are being processed.",
  COMPLETED: "Your annotations are ready.",
  COMPLETED_WITH_ERRORS: "Your partial results are ready.",
  FAILED: "Processing failed.",
};
async function render(progress) {
  if (expired) return;
  const response = await fetch(endpoint, { cache: "no-store" });
  if (response.status === 401)
    window.dispatchEvent(new Event("temu-session-expired"));
  if (response.status === 410) return expire();
  if (!response.ok) throw new Error("Status unavailable");
  const data = await response.json();
  $("heading").textContent = titles[data.status] || data.status;
  $("state").textContent = data.status;
  $("details").replaceChildren();
  for (const [name, value] of [
    ["Request ID", data.job_id],
    ["Submitted", new Date(data.created_at).toLocaleString()],
    ["Language", data.language],
    ["Documents", data.document_count],
    ["Entity types", data.entities.join(", ")],
    ["Queue position", data.queue_position ?? "—"],
  ]) {
    const dt = document.createElement("dt"),
      dd = document.createElement("dd");
    dt.textContent = name;
    dd.textContent = value;
    $("details").append(dt, dd);
  }
  $("status-message").textContent =
    data.error_summary ||
    (data.status === "COMPLETED_WITH_ERRORS"
      ? "Some documents failed. Downloads contain only validated annotated documents and an explicit partial manifest."
      : "");
  const available = progress.annotated_documents > 0;
  $("downloads").hidden = !available;
  $("explore").href = base + "/jobs/" + token + "/viewer";
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
      ["Documents", "documents"],
      ["Entities", "annotations"],
      ["Words", "words"],
      ["Tokens", "tokens"],
      ["Sentences", "sentences"],
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
  $("heading").textContent = "Your results have expired.";
  $("state").textContent = "EXPIRED";
  $("downloads").hidden = true;
}
const copy = document.createElement("button");
copy.className = "secondary";
copy.textContent = "Copy private link";
copy.onclick = () => navigator.clipboard.writeText(location.href);
$("details").after(copy);
startProgress(endpoint, { onChange: render, onExpire: expire });
