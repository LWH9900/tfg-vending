document.addEventListener("DOMContentLoaded", function () {
    const clickableElements = document.querySelectorAll(
        ".clickable-row, .clickable-card"
    );

    clickableElements.forEach(function (element) {
        element.addEventListener("click", function () {
            window.location.href = element.dataset.href;
        });

        element.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                window.location.href = element.dataset.href;
            }
        });
    });
});