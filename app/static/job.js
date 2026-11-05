const base = document.querySelector("meta[name=app-prefix]").content;
const token = location.pathname.split("/").pop();
const endpoint = base + "/api/jobs/" + encodeURIComponent(token);
const messages = {
  QUEUED: "Your request is queued.",
  PROCESSING: "Your documents are being processed.",
  COMPLETED: "Your annotations are ready.",
  FAILED: "Your request could not be completed.",
  EXPIRED: "Your results have expired.",
};
function details(rows) {
  const box = document.querySelector("#details");
  box.replaceChildren();
  for (const [label, text] of rows) {
    const dt = document.createElement("dt"),
      dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = text;
    box.append(dt, dd);
  }
}
async function poll() {
  try {
    const response = await fetch(endpoint, { cache: "no-store" });
    const data = await response.json();
    if (response.status === 410) {
      document.querySelector("#heading").textContent = messages.EXPIRED;
      document.querySelector("#state").textContent = "EXPIRED";
      return;
    }
    if (!response.ok)
      throw new Error(data.detail || "Could not load this request.");
    document.querySelector("#heading").textContent = messages[data.status];
    document.querySelector("#state").textContent = data.status;
    details([
      ["Request ID", data.job_id],
      ["Submitted", new Date(data.created_at).toLocaleString()],
      ["Language", data.language],
      ["Documents", data.document_count],
      ["Entity types", data.entities.join(", ")],
      ...(data.queue_position ? [["Queue position", data.queue_position]] : []),
    ]);
    document.querySelector("#status-message").textContent =
      data.error_summary ||
      (data.status === "PROCESSING"
        ? "Progress is reported when the entire batch finishes; no document estimate is available."
        : "");
    if (data.downloads_available) {
      document.querySelector("#downloads").hidden = false;
      document.querySelector("#explore").href = endpoint + "/viewer";
      document.querySelector("#brat").href = endpoint + "/download/brat";
      document.querySelector("#tsv").href = endpoint + "/download/tsv";
      document.querySelector("#statistics").href = endpoint + "/statistics";
      document.querySelector("#expiry").textContent =
        "Available until " + new Date(data.expires_at).toLocaleString();
      const summary = document.querySelector("#summary");
      summary.hidden = false;
      summary.replaceChildren();
      for (const [label, value] of [
        ["Documents", data.summary.documents],
        ["Entities", data.summary.annotations],
        ["Words", data.summary.words],
        ["Tokens", data.summary.tokens],
        ["Sentences", data.summary.sentences],
      ]) {
        const card = document.createElement("div"),
          number = document.createElement("strong"),
          name = document.createElement("span");
        number.textContent = value;
        name.textContent = label;
        card.append(number, name);
        summary.append(card);
      }
    }
    if (["QUEUED", "PROCESSING"].includes(data.status)) setTimeout(poll, 5000);
    // Expire the open page too, so stale download controls are hidden at the deadline.
    if (data.status === "COMPLETED")
      setTimeout(
        () => {
          document.querySelector("#downloads").hidden = true;
          poll();
        },
        Math.max(1, new Date(data.expires_at) - Date.now()),
      );
  } catch (exc) {
    document.querySelector("#status-message").textContent =
      exc.message + " Reload this page to retry.";
  }
}
poll();
