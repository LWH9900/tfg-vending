(function () {
    function normalizeHeader(value) {
        return value
            .toLocaleLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/\s+/g, " ")
            .trim();
    }

    function getColumnType(header) {
        if (header.includes("formato") && header.includes("unidad")) {
            return "format";
        }

        if (/^(nombre|producto|categoria|maquina|disposicion)\b/.test(header)) {
            return "clamp";
        }

        if (
            /(^iva\b|precio|importe|coste|valor|stock|cantidad|variacion|ajuste|unidades)/.test(
                header,
            )
        ) {
            return "nowrap";
        }

        return "wrap";
    }

    function addClampContent(cell) {
        if (
            cell.hasAttribute("colspan") ||
            cell.querySelector("button, input, select, textarea")
        ) {
            return;
        }

        const elementChildren = Array.from(cell.children);

        if (elementChildren.length === 0) {
            const text = cell.textContent.replace(/\s+/g, " ").trim();

            if (!text) {
                return;
            }

            const content = document.createElement("span");
            content.className = "table-cell__clamped-content";
            content.textContent = text;
            cell.replaceChildren(content);
        } else if (elementChildren.length === 1) {
            elementChildren[0].classList.add("table-cell__clamped-content");
        }
    }

    function classifyColumns(table) {
        if (table.classList.contains("editable-table")) {
            return;
        }

        const headers = Array.from(table.querySelectorAll("thead tr:first-child > th"));

        headers.forEach(function (header, columnIndex) {
            const type = getColumnType(normalizeHeader(header.textContent));
            const cells = [
                header,
                ...table.querySelectorAll(
                    `tbody tr > :nth-child(${columnIndex + 1}), ` +
                        `tfoot tr > :nth-child(${columnIndex + 1})`,
                ),
            ];

            cells.forEach(function (cell) {
                if (cell.hasAttribute("colspan")) {
                    return;
                }

                cell.classList.add("table-cell", `table-cell--${type}`);

                if (type === "clamp" && cell.tagName === "TD") {
                    addClampContent(cell);
                }
            });
        });
    }

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

        const table = wrapper.querySelector("table");

        if (table) {
            classifyColumns(table);
        }

        function updateTruncatedCellTitles() {
            wrapper
                .querySelectorAll("table:not(.editable-table) th, table:not(.editable-table) td")
                .forEach(function (cell) {
                    if (
                        cell.querySelector("button, input, select, textarea") ||
                        (cell.hasAttribute("title") &&
                            cell.dataset.generatedTableTitle !== "true")
                    ) {
                        return;
                    }

                    const descendants = Array.from(cell.querySelectorAll("*"));
                    const isTruncated =
                        cell.scrollWidth > cell.clientWidth + 1 ||
                        descendants.some(function (element) {
                            return element.scrollWidth > element.clientWidth + 1;
                        });

                    if (isTruncated) {
                        const text = cell.innerText.replace(/\s+/g, " ").trim();

                        if (text) {
                            cell.title = text;
                            cell.dataset.generatedTableTitle = "true";
                        }
                    } else if (cell.dataset.generatedTableTitle === "true") {
                        cell.removeAttribute("title");
                        delete cell.dataset.generatedTableTitle;
                    }
                });
        }

        function updateOverflow() {
            wrapper.classList.toggle(
                "is-overflowing",
                wrapper.scrollWidth > wrapper.clientWidth + 1,
            );
            updateTruncatedCellTitles();
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

            if (table) {
                resizeObserver.observe(table);
            }
        } else {
            window.addEventListener("resize", updateOverflow);
        }

        updateOverflow();
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".table-responsive").forEach(initialize);
    });
})();
