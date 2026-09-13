(function () {
    function normalize(value) {
        return value
            .toLocaleLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "");
    }

    function buildOption(option) {
        const item = document.createElement("button");
        const parts = option.textContent.trim().split(" · ");
        const title = document.createElement("span");

        item.type = "button";
        item.className = "product-select__option";
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", option.selected ? "true" : "false");
        item.dataset.value = option.value;
        item.dataset.search = normalize(option.textContent);

        title.className = "product-select__option-title";
        title.textContent = parts.shift() || option.textContent.trim();
        item.appendChild(title);

        if (parts.length) {
            const details = document.createElement("span");

            details.className = "product-select__option-details";
            details.textContent = parts.join(" / ");
            item.appendChild(details);
        }

        return item;
    }

    function initialize(select) {
        if (select.dataset.productSelectInitialized === "true") {
            return;
        }

        select.dataset.productSelectInitialized = "true";
        select.classList.add("product-search-select--native");

        const wrapper = document.createElement("div");
        const control = document.createElement("button");
        const menu = document.createElement("div");
        const search = document.createElement("input");
        const options = document.createElement("div");

        wrapper.className = "product-select";
        control.type = "button";
        control.className = "product-select__control";
        control.setAttribute("role", "combobox");
        control.setAttribute("aria-haspopup", "listbox");
        control.setAttribute("aria-expanded", "false");
        menu.className = "product-select__menu";
        menu.hidden = true;
        search.type = "search";
        search.className = "product-select__search form-control";
        search.placeholder = "Buscar producto";
        search.setAttribute("aria-label", "Buscar producto");
        options.className = "product-select__options";
        options.id = `${select.id || "product-select"}-options`;
        options.setAttribute("role", "listbox");
        control.setAttribute("aria-controls", options.id);

        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(select);
        wrapper.appendChild(control);
        wrapper.appendChild(menu);
        menu.appendChild(search);
        menu.appendChild(options);

        Array.from(select.options).forEach(function (option) {
            const item = buildOption(option);

            item.addEventListener("click", function () {
                select.value = item.dataset.value;
                select.dispatchEvent(new Event("change", { bubbles: true }));
                close();
            });

            options.appendChild(item);
        });

        function updateControl() {
            const selected = select.options[select.selectedIndex];
            const text = selected ? selected.textContent.trim() : "";
            const parts = text.split(" · ");

            control.replaceChildren();

            const title = document.createElement("span");
            title.className = "product-select__control-title";
            title.textContent = parts.shift() || "Selecciona un producto";
            control.appendChild(title);

            if (parts.length && selected.value) {
                const details = document.createElement("span");
                details.className = "product-select__control-details";
                details.textContent = parts.join(" / ");
                control.appendChild(details);
            }
        }

        function syncOptions() {
            options.querySelectorAll(".product-select__option").forEach(function (item, index) {
                const option = select.options[index];

                if (!option) {
                    return;
                }

                const parts = option.textContent.trim().split(" · ");
                const title = item.querySelector(".product-select__option-title");
                const details = item.querySelector(".product-select__option-details");

                item.dataset.search = normalize(option.textContent);
                item.setAttribute("aria-selected", option.selected ? "true" : "false");
                title.textContent = parts.shift() || option.textContent.trim();

                if (details) {
                    details.textContent = parts.join(" / ");
                }
            });

            updateControl();
        }

        function filterOptions() {
            const query = normalize(search.value.trim());
            let visibleCount = 0;

            options.querySelectorAll(".product-select__option").forEach(function (item) {
                const visible = !query || item.dataset.search.includes(query);
                item.hidden = !visible;
                visibleCount += visible ? 1 : 0;
            });

            options.classList.toggle("is-empty", visibleCount === 0);
        }

        function positionMenu() {
            const controlRect = control.getBoundingClientRect();
            const menuHeight = menu.offsetHeight;
            const spaceAbove = controlRect.top;
            const spaceBelow = window.innerHeight - controlRect.bottom;
            const shouldOpenUp =
                spaceBelow < menuHeight && spaceAbove > spaceBelow;

            menu.classList.toggle("product-select__menu--up", shouldOpenUp);
            menu.style.left = `${controlRect.left}px`;
            menu.style.width = `${controlRect.width}px`;
            menu.style.top = shouldOpenUp
                ? `${controlRect.top - menuHeight - 4}px`
                : `${controlRect.bottom + 4}px`;
        }

        function open() {
            document.body.appendChild(menu);
            menu.hidden = false;
            control.setAttribute("aria-expanded", "true");
            search.value = "";
            filterOptions();
            positionMenu();
            search.focus();
        }

        function close() {
            menu.hidden = true;
            control.setAttribute("aria-expanded", "false");
            wrapper.appendChild(menu);
            menu.style.left = "";
            menu.style.width = "";
            menu.style.top = "";
            updateControl();
        }

        control.addEventListener("click", function () {
            if (menu.hidden) {
                open();
            } else {
                close();
            }
        });

        search.addEventListener("input", filterOptions);
        select.addEventListener("change", syncOptions);
        window.addEventListener("resize", function () {
            if (!menu.hidden) {
                positionMenu();
            }
        });

        const optionObserver = new MutationObserver(syncOptions);
        optionObserver.observe(select, {
            childList: true,
            characterData: true,
            subtree: true,
        });

        document.addEventListener("click", function (event) {
            if (!wrapper.contains(event.target) && !menu.contains(event.target)) {
                close();
            }
        });

        updateControl();
    }

    function initializeAll(root) {
        root.querySelectorAll("select.product-search-select").forEach(initialize);
    }

    document.addEventListener("DOMContentLoaded", function () {
        initializeAll(document);

        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        initializeAll(node);
                    }
                });
            });
        });

        observer.observe(document.body, { childList: true, subtree: true });
    });
})();
