(function () {
    "use strict";

    function centralizeFeedback() {
        const feedback = document.getElementById("app-feedback");

        if (!feedback) {
            return;
        }

        function placeMessage(message) {
            if (
                message.closest(".modal") ||
                message.dataset.feedbackStatic !== undefined
            ) {
                return;
            }

            message.classList.add("app-feedback-message");
            message.setAttribute("role", "alert");

            if (
                message.dataset.feedbackDismissible !== undefined &&
                !message.querySelector('[data-bs-dismiss="alert"]')
            ) {
                const closeButton = document.createElement("button");
                closeButton.type = "button";
                closeButton.className = "btn-close";
                closeButton.dataset.bsDismiss = "alert";
                closeButton.setAttribute("aria-label", "Cerrar mensaje");
                message.appendChild(closeButton);
                message.classList.add("alert-dismissible");
            }

            if (!message.closest("#app-feedback")) {
                feedback.appendChild(message);
            }
        }

        document
            .querySelectorAll(".app-content .alert")
            .forEach(placeMessage);

        const content = document.querySelector(".app-content");

        if (content) {
            const observer = new MutationObserver((mutations) => {
                const hasNewAlerts = mutations.some((mutation) =>
                    Array.from(mutation.addedNodes).some(
                        (node) =>
                            node instanceof Element &&
                            (node.matches(".alert") || node.querySelector(".alert"))
                    )
                );

                if (hasNewAlerts) {
                    document
                        .querySelectorAll(".app-content .alert")
                        .forEach(placeMessage);
                }
            });

            observer.observe(content, { childList: true, subtree: true });
        }
    }

    function initializeConfirmations() {
        const modalElement = document.getElementById("appConfirmationModal");
        const messageElement = document.getElementById("appConfirmationModalMessage");
        const acceptButton = document.getElementById("appConfirmationAccept");

        if (!modalElement || !messageElement || !acceptButton || !window.bootstrap) {
            return;
        }

        const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
        const confirmedForms = new WeakSet();
        let pendingAction = null;

        function requestConfirmation(message, action, confirmLabel, danger) {
            messageElement.textContent = message;
            acceptButton.textContent = confirmLabel || "Confirmar";
            acceptButton.classList.toggle("btn-danger", danger);
            acceptButton.classList.toggle("btn-primary", !danger);
            pendingAction = action;
            modal.show();
        }

        document.addEventListener("submit", (event) => {
            const form = event.target;

            if (!(form instanceof HTMLFormElement) || confirmedForms.has(form)) {
                confirmedForms.delete(form);
                return;
            }

            const trigger = event.submitter;
            const message =
                trigger?.dataset.confirmMessage ||
                form.dataset.confirmMessage;

            if (!message) {
                return;
            }

            event.preventDefault();
            requestConfirmation(
                message,
                () => {
                    confirmedForms.add(form);
                    form.requestSubmit(trigger || undefined);
                },
                trigger?.dataset.confirmLabel || form.dataset.confirmLabel,
                trigger?.dataset.confirmDanger !== undefined ||
                    form.dataset.confirmDanger !== undefined
            );
        });

        document.addEventListener("click", (event) => {
            const link = event.target.closest("a[data-confirm-message]");

            if (!link) {
                return;
            }

            event.preventDefault();
            requestConfirmation(
                link.dataset.confirmMessage,
                () => window.location.assign(link.href),
                link.dataset.confirmLabel,
                link.dataset.confirmDanger !== undefined
            );
        });

        acceptButton.addEventListener("click", () => {
            const action = pendingAction;
            pendingAction = null;
            modal.hide();

            if (action) {
                action();
            }
        });

        modalElement.addEventListener("hidden.bs.modal", () => {
            pendingAction = null;
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        centralizeFeedback();
        initializeConfirmations();
    });
})();
