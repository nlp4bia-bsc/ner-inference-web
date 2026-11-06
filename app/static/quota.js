import { t, number, onLocaleChange } from "./auth.js";
let current;
export function paintQuota(value) {
  current = value;
  for (const node of document.querySelectorAll("[data-document-usage]"))
    node.textContent = `${number(value.occupied)} / ${value.limit == null ? "∞" : number(value.limit)}`;
  for (const node of document.querySelectorAll("[data-document-remaining]"))
    node.textContent =
      value.remaining == null
        ? t("No document quota limit")
        : t("{count} document slots available", {
            count: number(value.remaining),
          });
  for (const node of document.querySelectorAll("[data-upload-total]"))
    node.textContent = t("Total documents uploaded: {count}", {
      count: number(value.total_uploaded),
    });
  window.dispatchEvent(new CustomEvent("document-quota", { detail: value }));
}
onLocaleChange(() => {
  if (current) paintQuota(current);
});
