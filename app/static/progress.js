import {
  t,
  number,
  date,
  currentLocale,
  onLocaleChange,
  openDialog,
} from "./auth.js";
export const showDialog = openDialog;
/** Persisted document progress and monotonic server-clock countdown. */
export function startProgress(
  endpoint,
  { onChange = () => {}, onExpire = () => {} } = {},
) {
  const host = document.getElementById("global-progress"),
    panel = document.createElement("details");
  panel.open = true;
  panel.className = "global-progress";
  const summary = document.createElement("summary"),
    description = document.createElement("p"),
    bar = document.createElement("progress"),
    counts = document.createElement("p"),
    countdown = document.createElement("div");
  bar.max = 100;
  bar.value = 0;
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
    expired = false,
    latest = null;
  const terminal = ["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "EXPIRED"];
  function render() {
    bar.setAttribute("aria-label", t("Annotated document progress"));
    if (expired) {
      description.textContent = t("Results have expired.");
      summary.textContent = t("Expired");
      countdown.textContent = t(
        "Results have been deleted or are scheduled for deletion.",
      );
      return;
    }
    if (!latest) return;
    const data = latest;
    summary.textContent = `${t(data.status)} · ${new Intl.NumberFormat(currentLocale(), { maximumFractionDigits: 1 }).format(data.progress_percent)}% · ${t(panel.open ? "Hide progress" : "Show progress")}`;
    description.textContent =
      data.stage === "PREPARING_DOWNLOADS"
        ? t("Preparing downloads")
        : data.status === "QUEUED"
          ? t("Waiting in queue · Position: {count}", {
              count: data.queue_position ?? "—",
            })
          : data.status === "COMPLETED"
            ? t("All documents annotated successfully")
            : data.status === "COMPLETED_WITH_ERRORS"
              ? t(
                  "Completed with document errors · valid partial results available",
                )
              : data.status === "FAILED"
                ? t(
                    "Processing failed · published documents, if any, are partial results",
                  )
                : t("Processing your documents");
    bar.value = data.progress_percent;
    counts.textContent =
      t(
        "{done} / {total} annotated · {processing} processing · {pending} pending · {failed} failed",
        {
          done: number(data.annotated_documents),
          total: number(data.total_documents),
          processing: number(data.processing_documents),
          pending: number(data.pending_documents),
          failed: number(data.failed_documents),
        },
      ) +
      ". " +
      t("Document completion, not elapsed-time progress.");
  }
  panel.ontoggle = render;
  function expire() {
    if (expired) return;
    expired = true;
    stopped = true;
    clearTimeout(timer);
    clearInterval(clock);
    render();
    onExpire();
  }
  function tick() {
    if (expired) return;
    if (!deadline) {
      countdown.textContent = t(
        "72-hour availability begins after processing finishes.",
      );
      return;
    }
    const remaining =
      deadline.remaining - (performance.now() - deadline.observed);
    if (remaining <= 0) return expire();
    const seconds = Math.ceil(remaining / 1000),
      parts = [
        Math.floor(seconds / 86400),
        Math.floor(seconds / 3600) % 24,
        Math.floor(seconds / 60) % 60,
        seconds % 60,
      ];
    const label = document.createElement("span"),
      value = document.createElement("strong"),
      schedule = document.createElement("small");
    label.textContent = t("Results expire in");
    value.textContent = parts
      .map(
        (part, index) =>
          String(part).padStart(2, "0") + ["d", "h", "m", "s"][index],
      )
      .join(" : ");
    schedule.textContent =
      t("Scheduled deletion") + ": " + date(deadline.absolute);
    countdown.replaceChildren(label, value, schedule);
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
        }),
        data = await response.json();
      if (response.status === 401)
        window.dispatchEvent(new Event("temu-session-expired"));
      if (response.status === 410) {
        expire();
        return;
      }
      if (!response.ok) throw new Error();
      retries = 0;
      if (!latest && terminal.includes(data.status)) panel.open = false;
      latest = data;
      observedPending ||= ["QUEUED", "PROCESSING"].includes(data.status);
      render();
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
          const prefix = document.querySelector(
              "meta[name=app-prefix]",
            ).content,
            id = endpoint.split("/").pop(),
            viewer = prefix + "/jobs/" + id + "/viewer";
          const actions = [];
          if (data.annotated_documents > 0)
            actions.push({
              label: t("Explore annotations"),
              run: (dialog) => {
                if (location.pathname === viewer) {
                  dialog.close();
                  document.querySelector("#annotated-text")?.focus();
                } else location.assign(viewer + "?lang=" + currentLocale());
              },
            });
          if (["COMPLETED", "COMPLETED_WITH_ERRORS"].includes(data.status))
            for (const format of ["brat", "tsv"])
              actions.push({
                label: t(format === "brat" ? "Download BRAT" : "Download TSV"),
                run: () => location.assign(endpoint + "/download/" + format),
              });
          showDialog(
            t(
              data.status === "COMPLETED"
                ? "Annotations ready"
                : data.status === "COMPLETED_WITH_ERRORS"
                  ? "Partial results ready"
                  : "Processing failed",
            ),
            description.textContent,
            actions,
          );
        }
      }
      previous = data.status;
    } catch (_) {
      retries++;
      description.textContent = t(
        "Connection interrupted. Retrying automatically…",
      );
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
  onLocaleChange(() => {
    render();
    tick();
  });
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
