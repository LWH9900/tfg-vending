document.addEventListener("DOMContentLoaded", function () {
    const clickableElements = document.querySelectorAll(
        ".clickable-row, .clickable-card"
    );

    clickableElements.forEach(function (element) {
        const destination = element.dataset.href;

        if (!destination) {
            return;
        }

        const linkContainer = element.matches("tr")
            ? element.querySelector("td")
            : element;

        if (linkContainer) {
            const nativeLink = document.createElement("a");

            nativeLink.href = destination;
            nativeLink.className = "clickable-element-native-link";
            nativeLink.setAttribute("aria-label", "Abrir detalle");

            linkContainer.appendChild(nativeLink);
        }

        element.addEventListener("keydown", function (event) {
            if (event.key !== "Enter" && event.key !== " ") {
                return;
            }

            event.preventDefault();

            if (event.ctrlKey || event.metaKey || event.shiftKey) {
                window.open(
                    destination,
                    "_blank",
                    "noopener,noreferrer"
                );
                return;
            }

            window.location.href = destination;
        });
    });
});