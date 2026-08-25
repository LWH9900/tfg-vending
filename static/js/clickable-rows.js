document.addEventListener("DOMContentLoaded", function () {
    const rows = document.querySelectorAll(".clickable-row");

    rows.forEach(function (row) {
        row.addEventListener("click", function () {
            window.location.href = row.dataset.href;
        });

        row.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                window.location.href = row.dataset.href;
            }
        });
    });
});