import { confirmDeletion } from "./deletion.js";
const message = document.querySelector("#project-message");
for (const button of document.querySelectorAll("[data-delete-project]")) {
  button.onclick = () =>
    confirmDeletion(
      "/api/jobs/" + button.dataset.deleteProject,
      "Delete project",
      "This deletes all documents, annotations and downloads in this project and frees your quota. Upload history remains.",
      () => location.reload(),
      (error) => {
        message.textContent = error;
      },
      (busy) => {
        for (const control of document.querySelectorAll(
          "[data-delete-project]",
        ))
          control.disabled = busy;
      },
    );
}
