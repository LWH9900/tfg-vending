(function () {
    function initialize(wrapper) {
        if (wrapper.dataset.responsiveTableInitialized === "true") {
            return;
        }

        wrapper.dataset.responsiveTableInitialized = "true";
        wrapper.tabIndex = 0;
        wrapper.setAttribute("role", "region");

        if (!wrapper.hasAttribute("aria-label")) {
            wrapper.setAttribute("aria-label", "Tabla con desplazamiento horizontal");
        }

        function updateOverflow() {
            wrapper.classList.toggle(
                "is-overflowing",
                wrapper.scrollWidth > wrapper.clientWidth + 1,
            );
        }

        wrapper.addEventListener(
            "scroll",
            function () {
                if (Math.abs(wrapper.scrollLeft) > 8) {
                    wrapper.classList.add("has-scrolled");
                }
            },
            { passive: true },
        );

        if ("ResizeObserver" in window) {
            const resizeObserver = new ResizeObserver(updateOverflow);
            resizeObserver.observe(wrapper);
            resizeObserver.observe(wrapper.querySelector("table"));
        } else {
            window.addEventListener("resize", updateOverflow);
        }

        updateOverflow();
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".table-responsive").forEach(initialize);
    });
})();
