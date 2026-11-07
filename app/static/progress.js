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
    countdown = document.createElement("div"),
    worker = document.createElement("p"),
    models = document.createElement("div");
  worker.setAttribute("role", "status");
  models.className = "model-progress-list";
  bar.max = 100;
  bar.value = 0;
  description.setAttribute("role", "status");
  countdown.className = "countdown";
  panel.append(summary, description, worker, bar, counts, models, countdown);
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
  const phases = {
    PENDING: "Pending",
    CHECKING_CACHE: "Checking model availability",
    DOWNLOADING_MODEL: "Preparing models · downloading uncached checkpoints",
    LOADING_MODEL: "Loading model",
    ENCODING: "Encoding documents",
    INFERENCE: "Model inference progress",
    DECODING: "Preparing annotations",
    READY: "Ready",
    WAITING: "Waiting for next batch",
    WAITING_FOR_INDEX: "Waiting for terminology index",
    LOADING_INDEX: "Loading terminology index",
    READING_TERMINOLOGY: "Reading terminology",
    BUILDING_INDEX: "Building terminology index",
    SAVING_INDEX: "Writing terminology index",
    NORMALIZING: "Normalizing mentions",
  };
  let modelSignature = "";
  function renderModels(data) {
    const signature = JSON.stringify([currentLocale(), data.models]);
    if (signature === modelSignature) return;
    modelSignature = signature;
    models.replaceChildren();
    for (const model of data.models || []) {
      const card = document.createElement("section"),
        title = document.createElement("strong"),
        phase = document.createElement("p"),
        detail = document.createElement("small"),
        meter = document.createElement("progress"),
        activity = document.createElement("small");
      card.className = "model-progress-card";
      card.dataset.modelId = model.model_id;
      title.textContent = model.model_id;
      const finished = [
        "COMPLETED",
        "COMPLETED_WITH_ERRORS",
        "FAILED",
        "SKIPPED",
      ].includes(model.status);
      phase.textContent =
        (model.kind === "NORMALIZATION"
          ? t("Concept normalization") + " · "
          : "") +
        t(
          finished
            ? model.status === "SKIPPED"
              ? "Skipped"
              : model.status
            : phases[model.stage] || "Processing",
        );
      const parts = [];
      if (model.kind === "NER")
        parts.push(
          `${t("Documents")}: ${number(model.completed_documents)} / ${number(model.total_documents)}`,
        );
      if (model.failed_documents)
        parts.push(`${t("Failed")}: ${number(model.failed_documents)}`);
      if (model.batch_index)
        parts.push(
          `${t("Batch")}: ${number(model.batch_index)}${model.batch_count ? " / " + number(model.batch_count) : ""}`,
        );
      if (model.total_units != null)
        parts.push(
          `${t({ windows: "Windows", terms: "Terms", mentions: "Mentions" }[model.unit] || "Documents")}: ${number(model.completed_units)} / ${number(model.total_units)}`,
        );
      if (model.error_code) parts.push(model.error_code);
      detail.textContent = parts.join(" · ");
      meter.max = 100;
      meter.setAttribute(
        "aria-label",
        model.model_id + " · " + phase.textContent,
      );
      if (model.kind === "NORMALIZATION" && model.total_units)
        meter.value = (100 * model.completed_units) / model.total_units;
      else if (finished)
        meter.value =
          model.status === "COMPLETED" ? 100 : model.progress_percent;
      else if (model.stage === "INFERENCE" || model.stage === "WAITING")
        meter.value = model.progress_percent;
      // Downloads, loading and index preparation have no elapsed-time percentage.
      if (model.updated_at)
        activity.textContent =
          t("Last activity") + ": " + date(model.updated_at);
      card.append(title, phase, meter, detail, activity);
      models.append(card);
    }
  }
  function render() {
    const inference =
      latest?.status === "PROCESSING" &&
      latest?.models?.some((m) => m.kind === "NER");
    const percentage = inference
      ? latest.inference_percent
      : latest?.progress_percent;
    bar.setAttribute(
      "aria-label",
      t(inference ? "Model inference progress" : "Annotated document progress"),
    );
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
    host?.classList.toggle("progress-active", !terminal.includes(data.status));
    summary.textContent = `${t(data.status)} · ${inference ? t("Model inference progress") + ": " : ""}${new Intl.NumberFormat(currentLocale(), { maximumFractionDigits: 1 }).format(percentage)}% · ${t(panel.open ? "Hide progress" : "Show progress")}`;
    description.textContent =
      data.stage === "PREPARING_MODELS"
        ? t("Preparing models · downloading uncached checkpoints")
        : data.stage === "NORMALIZATION"
          ? t("Concept normalization")
          : data.stage === "PREPARING_DOWNLOADS"
            ? t("Preparing downloads")
            : data.status === "QUEUED"
              ? t("Waiting in queue · Position: {count}", {
                  count: data.queue_position ?? "—",
                })
              : data.status === "COMPLETED"
                ? t("All documents annotated successfully")
                : data.status === "COMPLETED_WITH_ERRORS"
                  ? t("Completed with errors · valid partial results available")
                  : data.status === "FAILED"
                    ? t(
                        "Processing failed · published documents, if any, are partial results",
                      )
                    : t("Processing your documents");
    bar.value = percentage;
    const unavailable =
      ["QUEUED", "PROCESSING"].includes(data.status) &&
      data.worker?.available === false;
    worker.className = unavailable ? "worker-unavailable" : "";
    worker.textContent = unavailable
      ? t(
          "Processing service unavailable. Start the worker using the same configuration.",
        )
      : data.status === "QUEUED" && data.worker?.state === "busy"
        ? t("The worker is processing another project.")
        : "";
    renderModels(data);
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
    host?.classList.remove("progress-active");
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
          document.hidden ? 30000 : Math.min(30000, 1000 * 2 ** retries),
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
