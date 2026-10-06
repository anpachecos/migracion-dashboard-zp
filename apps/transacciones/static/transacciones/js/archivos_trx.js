// Parámetros del Centro de archivos de Transacciones.
//
// Los trabajos reales los gestiona la cola persistente global del dashboard.
// Este módulo solo abre el diálogo y envía los parámetros al endpoint de cola.

window.TRX_ARCHIVOS = (function () {
    let raiz = null;
    let dialogo = null;
    let lista = null;
    let estado = null;
    let trabajoActual = null;
    let secuencia = 0;
    const trabajos = {};

    const REPORTES = {
        version_zona_paga: {
            titulo: "Versión Zona Paga",
            descripcion: "Configuración propia de la salida de Versión Zona Paga.",
        },
        informe_interno: {
            titulo: "Informe Interno TRX C2D",
            descripcion: "Elige el período del informe interno antes de generarlo.",
        },
        mayor_15: {
            titulo: null,
            descripcion: "El período y los filtros se definirán para este análisis.",
        },
        rezagadas: {
            titulo: "TRX REZAGADAS",
            descripcion: "El período y los filtros se definirán para este análisis.",
        },
    };

    function iniciar() {
        raiz = document.querySelector("[data-trx-archivos]");
        if (!raiz) { return false; }

        dialogo = document.querySelector("[data-trx-dlg-reporte]");
        lista = raiz.querySelector("[data-trx-cola-lista]");
        estado = raiz.querySelector("[data-trx-archivos-estado]");

        raiz.querySelectorAll("[data-trx-reporte]").forEach(function (boton) {
            boton.addEventListener("click", function () {
                abrirReporte(boton.getAttribute("data-trx-reporte"));
            });
        });

        const cerrar = dialogo && dialogo.querySelector("[data-trx-reporte-cerrar]");
        if (cerrar) {
            cerrar.addEventListener("click", function () { dialogo.close(); });
        }

        const enviar = dialogo && dialogo.querySelector("[data-trx-reporte-enviar]");
        if (enviar) {
            enviar.addEventListener("click", ponerEnCola);
        }

        const limpiar = raiz.querySelector("[data-trx-cola-limpiar]");
        if (limpiar) {
            limpiar.addEventListener("click", limpiarCola);
        }

        return true;
    }

    function abrirReporte(clave) {
        if (!dialogo || !REPORTES[clave]) { return; }

        trabajoActual = clave;
        const reporte = REPORTES[clave];
        const raizTrx = document.querySelector("[data-trx-raiz]");
        const umbral = raizTrx && raizTrx.getAttribute("data-umbral-corte-min");
        const titulo = reporte.titulo || "TRX >" + umbral + " MIN";
        dialogo.querySelector("[data-trx-reporte-titulo]").textContent = titulo;
        dialogo.querySelector("[data-trx-reporte-descripcion]").textContent = reporte.descripcion;
        const aviso = dialogo.querySelector("[data-trx-reporte-aviso]");
        if (aviso) { aviso.hidden = true; }
        dialogo.showModal();
    }

    function ponerEnCola() {
        if (!trabajoActual) { return; }

        const reporte = REPORTES[trabajoActual];
        const periodicidad = dialogo.querySelector("[data-trx-reporte-periodicidad]").value;
        const desde = dialogo.querySelector("[data-trx-reporte-desde]").value;
        const hasta = dialogo.querySelector("[data-trx-reporte-hasta]").value;
        const detalle = periodicidad + (desde ? " · " + desde : "") + (hasta ? " → " + hasta : "");

        const tipos = {
            informe_interno: "TRX_INFORME_INTERNO",
            mayor_15: "TRX_MAYOR_15",
            rezagadas: "TRX_REZAGADAS",
        };
        if (!window.DASHBOARD_TRABAJOS || !tipos[trabajoActual]) {
            const aviso = dialogo.querySelector("[data-trx-reporte-aviso]");
            if (aviso) {
                aviso.textContent = "Esta exportación todavía no está disponible.";
                aviso.hidden = false;
            }
            return;
        }
        dialogo.close();
        window.DASHBOARD_TRABAJOS.crear(tipos[trabajoActual], {
            periodicidad: periodicidad,
            fecha_desde: desde,
            fecha_hasta: hasta,
        }).then(function () {
            actualizarEstado("Trabajo enviado a la cola");
        }).catch(function (error) {
            actualizarEstado(error.message);
        });
    }

    function registrar(datos) {
        actualizarEstado("Trabajo enviado a la cola");
        return null;
    }

    function actualizarTrabajo(trabajo) {
        let fila = lista.querySelector('[data-trx-trabajo="' + trabajo.id + '"]');
        if (!fila) {
            fila = document.createElement("article");
            fila.className = "trx-trabajo";
            fila.setAttribute("data-trx-trabajo", trabajo.id);
            lista.prepend(fila);
        }

        fila.innerHTML = "";
        const encabezado = document.createElement("div");
        encabezado.className = "trx-trabajo-encabezado";
        encabezado.innerHTML = "<strong></strong><span></span>";
        encabezado.querySelector("strong").textContent = trabajo.titulo;
        encabezado.querySelector("span").textContent = trabajo.estado;

        const detalle = document.createElement("p");
        detalle.className = "trx-sub";
        detalle.textContent = trabajo.detalle;

        const barra = document.createElement("div");
        barra.className = "trx-trabajo-barra";
        const progreso = document.createElement("span");
        progreso.style.width = trabajo.progreso + "%";
        barra.appendChild(progreso);

        fila.appendChild(encabezado);
        fila.appendChild(detalle);
        fila.appendChild(barra);

        if (trabajo.accion) {
            const descargar = document.createElement("a");
            descargar.className = "trx-btn trx-btn-acento trx-trabajo-descargar";
            descargar.href = trabajo.accion.href;
            descargar.download = trabajo.accion.nombre;
            descargar.textContent = "Descargar";
            fila.appendChild(descargar);
        }
    }

    function actualizarEstado(texto) {
        if (estado) { estado.textContent = texto; }
    }

    function actualizarContador() {
        const contador = raiz && raiz.querySelector("[data-trx-cola-contador]");
        if (!contador) { return; }
        const listos = Object.keys(trabajos).filter(function (id) {
            return trabajos[id].accion;
        }).length;
        contador.textContent = listos;
        contador.hidden = listos === 0;
    }

    function limpiarCola() {
        Object.keys(trabajos).forEach(function (id) {
            const trabajo = trabajos[id];
            if (trabajo.accion) {
                window.URL.revokeObjectURL(trabajo.accion.href);
            }
            delete trabajos[id];
        });
        if (lista) { lista.textContent = ""; }
        const cola = raiz && raiz.querySelector("[data-trx-cola]");
        if (cola) { cola.hidden = true; }
        actualizarEstado("Listo para trabajar");
        actualizarContador();
    }

    return { iniciar: iniciar, registrar: registrar };
})();
