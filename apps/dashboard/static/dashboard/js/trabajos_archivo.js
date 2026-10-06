(function () {
    const cuerpo = document.body;
    const estadoUrl = cuerpo.dataset.trabajosEstadoUrl;
    const crearUrl = cuerpo.dataset.trabajosCrearUrl;
    const raiz = document.querySelector("[data-trabajos-notificaciones]");
    if (!raiz || !estadoUrl) return;

    const panel = raiz.querySelector("[data-trabajos-panel]");
    const lista = raiz.querySelector("[data-trabajos-lista]");
    const badge = raiz.querySelector("[data-trabajos-badge]");
    const toast = document.querySelector("[data-trabajos-toast]");
    const vistos = new Set(JSON.parse(sessionStorage.getItem("trabajos-toast-vistos") || "[]"));
    let activo = false;
    let temporizador = null;

    function csrf() {
        const encontrado = document.cookie.split(";").map(function (parte) {
            return parte.trim();
        }).find(function (parte) { return parte.indexOf("csrftoken=") === 0; });
        return encontrado ? decodeURIComponent(encontrado.split("=")[1]) : "";
    }

    function escalarToast(texto) {
        if (!toast) return;
        toast.textContent = texto;
        toast.hidden = false;
        window.clearTimeout(escalarToast.temporizador);
        escalarToast.temporizador = window.setTimeout(function () {
            toast.hidden = true;
        }, 7000);
    }

    function etiquetaTipo(tipo) {
        return {
            TRX_INFORME_INTERNO: "Informe Interno TRX C2D",
            TRX_MAYOR_15: "TRX sobre el umbral",
            TRX_REZAGADAS: "TRX rezagadas",
            PLANTILLA_IMPORTAR: "Importar plantilla",
            PLANTILLA_EXPORTAR: "Exportar plantilla",
        }[tipo] || tipo;
    }

    function etiquetaEstado(estado) {
        return {
            PENDIENTE: "Pendiente",
            PROCESANDO: "En proceso",
            LISTO: "Listo",
            ERROR: "Error",
            EXPIRADO: "Expirado",
        }[estado] || estado;
    }

    function pintar(trabajos) {
        lista.textContent = "";
        if (!trabajos.length) {
            lista.innerHTML = '<p class="dashboard-trabajos-vacio">No hay trabajos recientes.</p>';
            return;
        }
        trabajos.forEach(function (trabajo) {
            const item = document.createElement("article");
            item.className = "dashboard-trabajo dashboard-trabajo-" + trabajo.estado.toLowerCase();
            const titulo = document.createElement("strong");
            titulo.textContent = etiquetaTipo(trabajo.tipo);
            const estado = document.createElement("span");
            estado.textContent = etiquetaEstado(trabajo.estado);
            const mensaje = document.createElement("p");
            mensaje.textContent = trabajo.mensaje || "";
            item.append(titulo, estado, mensaje);
            if (trabajo.descarga) {
                const enlace = document.createElement("a");
                enlace.href = trabajo.descarga;
                enlace.className = "dashboard-trabajo-descargar";
                enlace.textContent = "Descargar";
                enlace.addEventListener("click", function () { marcarLeida(trabajo.id); });
                item.appendChild(enlace);
            }
            lista.appendChild(item);
        });
    }

    function marcarLeida(id) {
        fetch("/trabajos/" + id + "/leer/", {
            method: "POST",
            headers: { "X-CSRFToken": csrf(), "X-Requested-With": "fetch" },
        });
    }

    function consultar() {
        fetch(estadoUrl, { headers: { "X-Requested-With": "fetch" } })
            .then(function (respuesta) { return respuesta.ok ? respuesta.json() : null; })
            .then(function (datos) {
                if (!datos) return;
                pintar(datos.trabajos || []);
                if (!panel.hidden) {
                    (datos.trabajos || []).filter(function (trabajo) {
                        return !trabajo.leido;
                    }).forEach(function (trabajo) { marcarLeida(trabajo.id); });
                }
                badge.textContent = datos.no_leidos || 0;
                badge.hidden = !(datos.no_leidos > 0);
                const activos = (datos.trabajos || []).some(function (trabajo) {
                    return trabajo.estado === "PENDIENTE" || trabajo.estado === "PROCESANDO";
                });
                (datos.trabajos || []).filter(function (trabajo) {
                    return trabajo.estado === "LISTO" || trabajo.estado === "ERROR";
                }).forEach(function (trabajo) {
                    const clave = String(trabajo.id) + ":" + trabajo.estado;
                    if (!vistos.has(clave) && !trabajo.leido) {
                        vistos.add(clave);
                        if (trabajo.tipo === "PLANTILLA_IMPORTAR") {
                            escalarToast(trabajo.estado === "LISTO"
                                ? "Tu plantilla fue importada correctamente"
                                : "Falló la importación: " + trabajo.mensaje);
                        } else {
                            escalarToast(trabajo.estado === "LISTO"
                                ? "Tu archivo está listo"
                                : "Falló la exportación: " + trabajo.mensaje);
                        }
                    }
                });
                sessionStorage.setItem("trabajos-toast-vistos", JSON.stringify(Array.from(vistos).slice(-100)));
                if (activos && !activo) iniciarPolling();
                if (!activos && activo) detenerPolling();
            });
    }

    function iniciarPolling() {
        activo = true;
        if (!temporizador) temporizador = window.setInterval(consultar, 5000);
    }

    function detenerPolling() {
        activo = false;
        window.clearInterval(temporizador);
        temporizador = null;
    }

    raiz.querySelector("[data-trabajos-toggle]").addEventListener("click", function () {
        panel.hidden = !panel.hidden;
        this.setAttribute("aria-expanded", String(!panel.hidden));
        if (!panel.hidden) consultar();
    });
    raiz.querySelector("[data-trabajos-cerrar]").addEventListener("click", function () {
        panel.hidden = true;
        raiz.querySelector("[data-trabajos-toggle]").setAttribute("aria-expanded", "false");
    });

    window.DASHBOARD_TRABAJOS = {
        avisar: escalarToast,
        crear: function (tipo, parametros) {
            const datos = new FormData();
            datos.append("tipo", tipo);
            datos.append("parametros", JSON.stringify(parametros || {}));
            return fetch(crearUrl, {
                method: "POST",
                body: datos,
                headers: { "X-CSRFToken": csrf(), "X-Requested-With": "fetch" },
            }).then(function (respuesta) {
                if (!respuesta.ok) return respuesta.json().then(function (error) { throw new Error(error.error); });
                iniciarPolling();
                consultar();
                return respuesta.json();
            });
        },
    };

    consultar();
})();
