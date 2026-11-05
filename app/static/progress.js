let dialogSequence = 0;
/** Persisted progress and server-clock countdown shared by status and viewer pages. */
export function showDialog(title, message, actions = []) {
  const dialog = document.createElement("dialog");
  dialog.className = "notification-dialog";
  const heading = document.createElement("h2");
  heading.textContent = title;
  heading.id = `notification-title-${++dialogSequence}`;
  dialog.setAttribute("aria-labelledby", heading.id);
  const text = document.createElement("p");
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
  close.textContent = "Close";
  close.onclick = () => dialog.close();
  dialog.append(close);
  dialog.addEventListener("close", () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
  return dialog;
}
export function startProgress(
  endpoint,
  { onChange = () => {}, onExpire = () => {} } = {},
) {
  const host = document.getElementById("global-progress");
  const panel = document.createElement("details");
  panel.open = true;
  panel.className = "global-progress";
  const summary = document.createElement("summary"),
    description = document.createElement("p"),
    bar = document.createElement("progress"),
    counts = document.createElement("p"),
    countdown = document.createElement("p");
  bar.max = 100;
  bar.value = 0;
  bar.setAttribute("aria-label", "Annotated document progress");
  description.setAttribute("role", "status");
  countdown.className = "countdown";
  panel.append(summary, description, bar, counts, countdown);
  host?.append(panel);
  let stopped = false,
    polling = false,
    timer,
    retries = 0,
    deadline = null,
    previous = null,
    observedPending = false,
    expired = false;
  const terminal = ["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "EXPIRED"];
  function expire() {
    if (expired) return;
    expired = true;
    stopped = true;
    clearTimeout(timer);
    clearInterval(clock);
    description.textContent = "Results have expired.";
    summary.textContent = "Expired";
    countdown.textContent =
      "Results have been deleted or are scheduled for deletion.";
    onExpire();
  }
  function tick() {
    if (!deadline) {
      countdown.textContent =
        "72-hour availability begins after processing finishes.";
      return;
    }
    const remaining =
      deadline.remaining - (performance.now() - deadline.observed);
    if (remaining <= 0) return expire();
    const seconds = Math.ceil(remaining / 1000),
      days = Math.floor(seconds / 86400),
      hours = Math.floor(seconds / 3600) % 24,
      minutes = Math.floor(seconds / 60) % 60;
    countdown.textContent = `Your results will be deleted in: ${days} days : ${hours} hours : ${minutes} minutes : ${seconds % 60} seconds. Scheduled deletion: ${new Date(deadline.absolute).toLocaleString()}`;
    countdown.className =
      "countdown " +
      (remaining < 3600000 ? "urgent" : remaining < 86400000 ? "warning" : "");
  }
  const clock = setInterval(tick, 1000);
  async function poll() {
    if (stopped || polling) return;
    polling = true;
    clearTimeout(timer);
    try {
      const response = await fetch(endpoint + "/progress", {
        cache: "no-store",
      });
      const data = await response.json();
      if (response.status === 410) {
        expire();
        return;
      }
      if (!response.ok) throw new Error();
      retries = 0;
      observedPending ||= ["QUEUED", "PROCESSING"].includes(data.status);
      summary.textContent = `${data.status} · ${data.progress_percent.toFixed(1)}% · ${panel.open ? "Hide progress" : "Show progress"}`;
      panel.ontoggle = () => {
        summary.textContent = `${data.status} · ${data.progress_percent.toFixed(1)}% · ${panel.open ? "Hide progress" : "Show progress"}`;
      };
      description.textContent =
        data.stage === "PREPARING_DOWNLOADS"
          ? "Preparing downloads"
          : data.status === "QUEUED"
            ? `Waiting in queue · Position: ${data.queue_position ?? "—"}`
            : data.status === "COMPLETED"
              ? "All documents annotated successfully"
              : data.status === "COMPLETED_WITH_ERRORS"
                ? "Completed with document errors · valid partial results available"
                : data.status === "FAILED"
                  ? "Processing failed · published documents, if any, are partial results"
                  : "Processing your documents";
      bar.value = data.progress_percent;
      counts.textContent = `${data.annotated_documents} / ${data.total_documents} annotated · ${data.processing_documents} processing · ${data.pending_documents} pending · ${data.failed_documents} failed. This is document completion, not elapsed-time progress.`;
      if (data.expires_at)
        deadline = {
          remaining: Date.parse(data.expires_at) - Date.parse(data.server_now),
          observed: performance.now(),
          absolute: data.expires_at,
        };
      tick();
      await onChange(data);
      if (terminal.includes(data.status)) {
        stopped = true;
        if (observedPending && previous !== data.status) {
          showDialog(
            data.status === "COMPLETED"
              ? "Annotations ready"
              : data.status === "COMPLETED_WITH_ERRORS"
                ? "Partial results ready"
                : "Processing failed",
            description.textContent,
          );
        }
      }
      previous = data.status;
    } catch (_) {
      retries++;
      description.textContent =
        "Connection interrupted. Retrying automatically…";
    } finally {
      polling = false;
      if (!stopped)
        timer = setTimeout(
          poll,
          document.hidden ? 30000 : Math.min(30000, 2500 * 2 ** retries),
        );
    }
  }
  const refresh = () => {
    if (!document.hidden && !stopped) poll();
  };
  document.addEventListener("visibilitychange", refresh);
  window.addEventListener("focus", refresh);
  poll();
  return {
    refresh: poll,
    stop() {
      stopped = true;
      clearTimeout(timer);
      clearInterval(clock);
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener("focus", refresh);
    },
  };
}
