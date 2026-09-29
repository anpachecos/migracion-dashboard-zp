document.addEventListener("DOMContentLoaded", function () {
    const CLAVE = "zp.sidebar.grupos";
    const nav = document.querySelector(".sidebar-nav");

    if (!nav) {
        return;
    }

    const grupos = Array.from(nav.querySelectorAll("details[data-grupo]"));

    function leerPreferencias() {
        try {
            return JSON.parse(window.localStorage.getItem(CLAVE) || "{}") || {};
        } catch (error) {
            return {};
        }
    }

    function guardarPreferencias(preferencias) {
        try {
            window.localStorage.setItem(CLAVE, JSON.stringify(preferencias));
        } catch (error) {
            if (window.console && window.console.debug) {
                window.console.debug("Sidebar: sin almacenamiento local disponible.");
            }
        }
    }

    const preferencias = leerPreferencias();

    grupos.forEach(function (grupo) {
        if (grupo.hasAttribute("data-activo")) {
            return;
        }

        const nombre = grupo.dataset.grupo;

        if (Object.prototype.hasOwnProperty.call(preferencias, nombre)) {
            grupo.open = preferencias[nombre] === true;
        }
    });

    grupos.forEach(function (grupo) {
        grupo.addEventListener("toggle", function () {
            const actuales = leerPreferencias();

            actuales[grupo.dataset.grupo] = grupo.open;
            guardarPreferencias(actuales);
        });
    });
});
