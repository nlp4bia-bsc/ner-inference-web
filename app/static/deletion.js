import { t, openDialog } from "./auth.js";
import { paintQuota } from "./quota.js";
const base = document.querySelector('meta[name="app-prefix"]').content;
export function confirmDeletion(
  endpoint,
  title,
  description,
  onDeleted,
  onError,
  onBusy = () => {},
  documents,
) {
  return openDialog(t(title), t(description), [
    {
      label: t("Delete"),
      run: async (dialog) => {
        dialog.close();
        onBusy(true);
        try {
          const session = await fetch(base + "/api/auth/session", {
            cache: "no-store",
          });
          if (session.status === 401) {
            window.dispatchEvent(new Event("temu-session-expired"));
            return;
          }
          if (!session.ok)
            throw new Error(
              t(
                "The service is temporarily unavailable. Please try again later.",
              ),
            );
          const identity = await session.json();
          const response = await fetch(base + endpoint, {
            method: documents === undefined ? "DELETE" : "POST",
            headers: {
              "X-CSRF-Token": identity.csrf_token,
              ...(documents !== undefined
                ? { "Content-Type": "application/json" }
                : {}),
            },
            ...(documents !== undefined
              ? { body: JSON.stringify({ documents }) }
              : {}),
          });
          if (response.status === 401) {
            window.dispatchEvent(new Event("temu-session-expired"));
            return;
          }
          const result = await response.json();
          if (!response.ok)
            throw new Error(
              typeof result.detail === "string"
                ? t(result.detail)
                : t("The request could not be submitted. Please try again."),
            );
          paintQuota(result.quota);
          await onDeleted(result);
        } catch (error) {
          onError(
            error.message ||
              t("The request could not be submitted. Please try again."),
          );
        } finally {
          onBusy(false);
        }
      },
    },
  ]);
}
