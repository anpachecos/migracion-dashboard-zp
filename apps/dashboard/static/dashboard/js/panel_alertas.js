document.addEventListener("DOMContentLoaded", function () {
    const btnSeleccionar = document.getElementById("btn-seleccionar-ubicaciones");
    const btnDeseleccionar = document.getElementById("btn-deseleccionar-ubicaciones");
    const buscador = document.getElementById("buscador-ubicaciones");

    const obtenerCheckboxes = function () {
        return Array.from(document.querySelectorAll(".checkbox-ubicacion"));
    };

    const obtenerItems = function () {
        return Array.from(document.querySelectorAll(".filtro-ubicacion-item"));
    };

    if (btnSeleccionar) {
        btnSeleccionar.addEventListener("click", function () {
            obtenerCheckboxes().forEach(function (checkbox) {
                const item = checkbox.closest(".filtro-ubicacion-item");

                if (!item || !item.classList.contains("oculto")) {
                    checkbox.checked = true;
                }
            });
        });
    }

    if (btnDeseleccionar) {
        btnDeseleccionar.addEventListener("click", function () {
            obtenerCheckboxes().forEach(function (checkbox) {
                const item = checkbox.closest(".filtro-ubicacion-item");

                if (!item || !item.classList.contains("oculto")) {
                    checkbox.checked = false;
                }
            });
        });
    }

    if (buscador) {
        buscador.addEventListener("input", function () {
            const textoBusqueda = buscador.value
                .toLowerCase()
                .normalize("NFD")
                .replace(/[\u0300-\u036f]/g, "")
                .trim();

            obtenerItems().forEach(function (item) {
                const textoItem = item.textContent
                    .toLowerCase()
                    .normalize("NFD")
                    .replace(/[\u0300-\u036f]/g, "");

                if (textoItem.includes(textoBusqueda)) {
                    item.classList.remove("oculto");
                } else {
                    item.classList.add("oculto");
                }
            });
        });
    }
});