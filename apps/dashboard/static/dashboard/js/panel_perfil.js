(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        const shell = document.querySelector("[data-reglas-shell]");
        if (!shell) return;

        const toggle = shell.querySelector("[data-toggle-reglas]");
        const container = shell.querySelector("[data-editor-reglas]");
        if (!toggle || !container) return;

        let loaded = false;
        let loading = false;

        function setOpen(open) {
            shell.classList.toggle("is-open", open);
            container.hidden = !open;
            toggle.setAttribute("aria-expanded", String(open));
            const label = toggle.querySelector("[data-toggle-reglas-texto]");
            if (label) label.textContent = open ? "Cerrar configuración" : "Administrar reglas";
        }

        async function loadEditor(force) {
            if ((loaded && !force) || loading) return;
            loading = true;
            container.innerHTML = '<div class="reglas-editor-cargando"><span></span>Cargando reglas desde Oracle…</div>';

            try {
                const response = await fetch(shell.dataset.editorUrl, {
                    headers: {"X-Requested-With": "XMLHttpRequest"},
                    credentials: "same-origin"
                });
                container.innerHTML = await response.text();
                loaded = response.ok;
                bindEditor(container);
                const retry = container.querySelector("[data-reintentar-reglas]");
                if (retry) retry.addEventListener("click", function () { loadEditor(true); });
            } catch (error) {
                loaded = false;
                container.innerHTML = '<div class="reglas-editor-error"><strong>No fue posible cargar el editor.</strong><p>Revisa la conexión e inténtalo nuevamente.</p><button type="button" class="btn-reglas-secundario" data-reintentar-reglas>Reintentar</button></div>';
                container.querySelector("[data-reintentar-reglas]").addEventListener("click", function () { loadEditor(true); });
            } finally {
                loading = false;
            }
        }

        toggle.addEventListener("click", function () {
            const open = !shell.classList.contains("is-open");
            setOpen(open);
            if (open) loadEditor(false);
        });

        if (shell.dataset.autoOpen === "1") {
            setOpen(true);
            loadEditor(false);
        } else {
            setOpen(false);
        }
    });

    function bindEditor(root) {
        const form = root.querySelector("[data-reglas-form]");
        if (!form) return;

        root.querySelectorAll("[data-reglas-tab]").forEach(function (tab) {
            tab.addEventListener("click", function () {
                const selected = tab.dataset.reglasTab;
                root.querySelectorAll("[data-reglas-tab]").forEach(function (item) {
                    const active = item === tab;
                    item.classList.toggle("is-active", active);
                    item.setAttribute("aria-selected", String(active));
                });
                root.querySelectorAll("[data-reglas-panel]").forEach(function (panel) {
                    const active = panel.dataset.reglasPanel === selected;
                    panel.classList.toggle("is-active", active);
                    panel.hidden = !active;
                });
            });
        });

        const inputs = Array.from(form.querySelectorAll("[data-regla-input]"));
        inputs.forEach(function (input) {
            const card = input.closest("[data-regla-card]");
            const slider = card.querySelector("[data-regla-slider]");

            input.addEventListener("input", function () {
                if (slider) slider.value = input.value;
                updateRule(card, input);
                updateRanges(form);
                updateChanged(form, inputs);

            });

            if (slider) {
                slider.addEventListener("input", function () {
                    input.value = slider.value;
                    input.dispatchEvent(new Event("input", {bubbles: true}));
                });
            }

            updateRule(card, input);
        });


        updateRanges(form);
        updateChanged(form, inputs);

        form.addEventListener("submit", function (event) {
            const submitter = event.submitter;
            if (submitter && submitter.value === "guardar_y_recalcular_alertas") {
                const ok = window.confirm(
                    "Se guardarán los cambios y se iniciará el recálculo correspondiente en segundo plano. ¿Deseas continuar?"
                );
                if (!ok) event.preventDefault();
            }
        });
    }

function numericValue(value) {
        const normalized = String(value).trim().replace(",", ".");
        if (normalized === "") return null;
        const parsed = Number(normalized);
        return Number.isFinite(parsed) ? parsed : normalized;
    }
    function updateRule(card, input) {
        const explanation = card.querySelector("[data-regla-explicacion]");
        if (explanation) {
            explanation.textContent = explanation.dataset.template.replace("{valor}", input.value || "—");
        }
        const changed = numericValue(input.value) !== numericValue(card.dataset.original);
        card.classList.toggle("is-changed", changed);
    }

    function updateRanges(form) {
        form.querySelectorAll("[data-reglas-rango]").forEach(function (range) {
            const markers = Array.from(range.querySelectorAll("[data-rango-clave]"));
            const values = markers.map(function (marker) {
                const input = form.querySelector('[name="regla_' + marker.dataset.rangoClave + '"]');
                return input ? numericValue(input.value) : 0;
            });
            const fixedMax = numericValue(range.dataset.maximoFijo);
            const highest = Math.max.apply(null, values.map(function (value) {
                return typeof value === "number" ? value : 0;
            }));
            const scaleMax = fixedMax || Math.max(1, highest * 1.15);

            markers.forEach(function (marker, index) {
                const value = typeof values[index] === "number" ? values[index] : 0;
                marker.style.left = Math.max(0, Math.min(100, (value / scaleMax) * 100)) + "%";
                const label = range.querySelector('[data-rango-valor="' + marker.dataset.rangoClave + '"]');
                if (label) label.textContent = value;
            });
        });
    }
    function updateChanged(form, inputs) {
        const count = inputs.filter(function (input) {
            const card = input.closest("[data-regla-card]");
            return numericValue(input.value) !== numericValue(card.dataset.original);
        }).length;
        const counter = form.querySelector("[data-contador-cambios]");
        if (!counter) return;
        counter.textContent = count === 0 ? "Sin cambios pendientes" : count + (count === 1 ? " cambio pendiente" : " cambios pendientes");
        counter.classList.toggle("has-changes", count > 0);
    }

})();
