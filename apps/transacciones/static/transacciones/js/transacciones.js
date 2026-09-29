/*
 * Módulo de Transacciones.
 *
 * En el hito 1 el módulo es GET puro: las pestañas son enlaces, los filtros son
 * un formulario GET y las tablas se renderizan en el servidor. No hay gráficos
 * ni paginación del lado del cliente.
 *
 * Este archivo solo evita el error de rango más común: si la persona indica
 * "Desde" pero deja "Hasta" vacío, el backend interpreta el rango como un solo
 * día, lo que no siempre es lo que se quiso escribir. La sincronización es
 * reversible y no reemplaza la validación del servidor.
 */
(function () {
    "use strict";

    function sincronizarHasta() {
        var desde = document.getElementById("trx-fecha-desde");
        var hasta = document.getElementById("trx-fecha-hasta");

        if (!desde || !hasta) {
            return;
        }

        if (desde.value && !hasta.value) {
            hasta.value = desde.value;
        }
    }

    function init() {
        var desde = document.getElementById("trx-fecha-desde");
        var hasta = document.getElementById("trx-fecha-hasta");

        if (!desde || !hasta) {
            return;
        }

        desde.addEventListener("change", sincronizarHasta);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
