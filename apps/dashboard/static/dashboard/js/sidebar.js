/*
 * Sidebar del dashboard: estado de los grupos, refresco y reloj de antigüedad.
 *
 * El agrupamiento en <details> es nativo: sin este archivo los grupos siguen
 * plegándose. Acá solo se recuerda en localStorage qué grupos dejó el usuario
 * cerrados y se mantiene al día el texto de antigüedad de los datos.
 */

document.addEventListener("DOMContentLoaded", function () {
    const CLAVE_GRUPOS = "zp.sidebar.grupos";
    const INTERVALO_RELOJ = 30000;

    function leerPreferencias(clave) {
        try {
            return window.localStorage.getItem(clave);
        } catch (error) {
            return null;
        }
    }

    function guardarPreferencias(clave, valor) {
        try {
            window.localStorage.setItem(clave, valor);
        } catch (error) {
            if (window.console && window.console.debug) {
                window.console.debug("Sidebar: sin almacenamiento local disponible.");
            }
        }
    }

    function leerGruposGuardados() {
        try {
            return JSON.parse(leerPreferencias(CLAVE_GRUPOS) || "{}") || {};
        } catch (error) {
            return {};
        }
    }

    function guardarGrupos(grupos) {
        guardarPreferencias(CLAVE_GRUPOS, JSON.stringify(grupos));
    }

    /*
     * Estado de los grupos: se respeta lo elegido por el usuario, salvo que la
     * página activa esté dentro del grupo, que siempre queda abierto.
     */
    function aplicarGrupos(elementos, preferencias) {
        elementos.forEach(function (grupo) {
            if (grupo.hasAttribute("data-activo")) {
                grupo.open = true;
                return;
            }

            const nombre = grupo.dataset.grupo;

            if (Object.prototype.hasOwnProperty.call(preferencias, nombre)) {
                grupo.open = preferencias[nombre] === true;
            }
        });
    }

    const nav = document.querySelector(".sidebar-nav");

    if (nav) {
        const grupos = Array.from(nav.querySelectorAll("details[data-grupo]"));

        aplicarGrupos(grupos, leerGruposGuardados());

        grupos.forEach(function (grupo) {
            grupo.addEventListener("toggle", function () {
                const actuales = leerGruposGuardados();
                actuales[grupo.dataset.grupo] = grupo.open;
                guardarGrupos(actuales);
            });
        });
    }

    const botonRefrescar = document.querySelector("[data-sidebar-refresh]");

    if (botonRefrescar) {
        botonRefrescar.addEventListener("click", function () {
            window.location.reload();
        });
    }

    /*
     * Reloj de antigüedad. El texto se pinta en el servidor y los umbrales
     * viajan en el DOM, así que la política no está repetida acá: se recalcula
     * en el navegador para que "hace 4 min" no envejezca en una pestaña
     * abierta toda la mañana. La fecha absoluta vive en el title de cada chip y
     * se actualiza con ella, para que no contradiga al texto visible.
     */
    const contenedor = document.querySelector("[data-sidebar-reloj]");

    if (contenedor) {
        const tarjetas = Array.from(contenedor.querySelectorAll("[data-epoch]")).filter(
            function (tarjeta) {
                return tarjeta.dataset.epoch;
            }
        );

        function textoRelativo(segundos) {
            if (segundos < 60) {
                return "hace instantes";
            }

            if (segundos < 3600) {
                return "hace " + Math.floor(segundos / 60) + " min";
            }

            if (segundos < 86400) {
                return "hace " + Math.floor(segundos / 3600) + " h";
            }

            return "hace " + Math.floor(segundos / 86400) + " días";
        }

        function estadoSegun(minutos, umbralAviso, umbralError) {
            if (minutos >= umbralError) {
                return "error";
            }

            if (minutos >= umbralAviso) {
                return "aviso";
            }

            return "ok";
        }

        function actualizarReloj() {
            const ahora = Math.floor(Date.now() / 1000);

            tarjetas.forEach(function (tarjeta) {
                const epoch = Number(tarjeta.dataset.epoch);

                if (!Number.isFinite(epoch) || epoch <= 0) {
                    return;
                }

                const segundos = Math.max(0, ahora - epoch);
                const umbralAviso = Number(tarjeta.dataset.umbralAviso) || 60;
                const umbralError = Number(tarjeta.dataset.umbralError) || 180;
                const estado = estadoSegun(Math.floor(segundos / 60), umbralAviso, umbralError);
                const relativo = textoRelativo(segundos);
                const destino = tarjeta.querySelector("[data-epoch-texto]");

                if (destino) {
                    destino.textContent = relativo;
                }

                if (tarjeta.dataset.epochAbsoluto) {
                    tarjeta.title = tarjeta.dataset.epochAbsoluto + " · " + relativo;
                }

                tarjeta.classList.remove(
                    "sidebar-status-ok",
                    "sidebar-status-aviso",
                    "sidebar-status-error"
                );
                tarjeta.classList.add("sidebar-status-" + estado);
            });
        }

        if (tarjetas.length) {
            actualizarReloj();
            window.setInterval(actualizarReloj, INTERVALO_RELOJ);
        }
    }
});
