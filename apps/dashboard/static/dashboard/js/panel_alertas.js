document.addEventListener("DOMContentLoaded", function () {
    const formulario = document.getElementById("preferencias-alertas-form");

    if (!formulario) {
        return;
    }

    const urlSugerencias = formulario.dataset.sugerenciasUrl;
    const minimoCaracteres = Number(formulario.dataset.minimoCaracteres || 2);
    const campoAmids = formulario.querySelector("[data-campo-amids]");
    const resumen = document.getElementById("preferencias-resumen");

    const configuraciones = {
        amid: {
            lista: formulario.querySelector('[data-lista-exclusiones="amid"]'),
            vacio: formulario.querySelector('[data-lista-vacia="amid"]'),
        },
        ubicacion: {
            lista: formulario.querySelector('[data-lista-exclusiones="ubicacion"]'),
            vacio: formulario.querySelector('[data-lista-vacia="ubicacion"]'),
        },
    };

    const obtenerChips = function (tipo) {
        return Array.from(
            configuraciones[tipo].lista.querySelectorAll(".preferencia-chip")
        );
    };

    const obtenerValores = function (tipo) {
        return obtenerChips(tipo).map(function (chip) {
            return chip.dataset.valor;
        });
    };

    const estaSeleccionado = function (tipo, valor) {
        return obtenerValores(tipo).includes(String(valor));
    };

    const actualizarEstado = function () {
        const amids = obtenerValores("amid");
        const ubicaciones = obtenerValores("ubicacion");

        campoAmids.value = amids.join(",");
        configuraciones.amid.vacio.hidden = amids.length > 0;
        configuraciones.ubicacion.vacio.hidden = ubicaciones.length > 0;

        if (resumen) {
            const total = amids.length + ubicaciones.length;
            const textoTotal = total === 1
                ? "1 exclusión activa"
                : `${total} exclusiones activas`;
            const textoUbicaciones = ubicaciones.length === 1
                ? "1 ubicación"
                : `${ubicaciones.length} ubicaciones`;

            resumen.textContent = `${textoTotal} · ${amids.length} AMID · ${textoUbicaciones}`;
        }
    };

    const crearChip = function (tipo, valor, etiqueta) {
        valor = String(valor);

        if (!valor || estaSeleccionado(tipo, valor)) {
            return false;
        }

        const chip = document.createElement("span");
        chip.className = "preferencia-chip";
        chip.dataset.valor = valor;

        if (tipo === "ubicacion") {
            chip.classList.add("preferencia-chip-ubicacion");
        }

        const texto = document.createElement("span");
        texto.textContent = etiqueta || valor;
        chip.appendChild(texto);

        const botonQuitar = document.createElement("button");
        botonQuitar.type = "button";
        botonQuitar.dataset.quitarExclusion = "";
        botonQuitar.innerHTML = "&times;";
        botonQuitar.setAttribute(
            "aria-label",
            tipo === "amid"
                ? `Quitar AMID ${etiqueta || valor}`
                : `Quitar ubicación ${etiqueta || valor}`
        );
        chip.appendChild(botonQuitar);

        if (tipo === "ubicacion") {
            const campoOculto = document.createElement("input");
            campoOculto.type = "hidden";
            campoOculto.name = "ubicaciones_excluidas";
            campoOculto.value = valor;
            chip.appendChild(campoOculto);
        }

        configuraciones[tipo].lista.insertBefore(
            chip,
            configuraciones[tipo].vacio
        );
        actualizarEstado();
        return true;
    };

    formulario.addEventListener("click", function (evento) {
        const botonQuitar = evento.target.closest("[data-quitar-exclusion]");

        if (!botonQuitar) {
            return;
        }

        const chip = botonQuitar.closest(".preferencia-chip");
        if (chip) {
            chip.remove();
            actualizarEstado();
        }
    });

    const cerrarSugerencias = function (contenedor, sugerencias) {
        sugerencias.hidden = true;
        sugerencias.replaceChildren();
        contenedor.dataset.indiceActivo = "-1";
    };

    const activarSugerencia = function (contenedor, sugerencias, indice) {
        const opciones = Array.from(
            sugerencias.querySelectorAll(".preferencia-sugerencia")
        );

        if (!opciones.length) {
            return;
        }

        const indiceNormalizado = (indice + opciones.length) % opciones.length;
        opciones.forEach(function (opcion, posicion) {
            const activa = posicion === indiceNormalizado;
            opcion.classList.toggle("activa", activa);
            opcion.setAttribute("aria-selected", activa ? "true" : "false");
        });
        contenedor.dataset.indiceActivo = String(indiceNormalizado);
    };

    const inicializarAutocomplete = function (contenedor) {
        const tipo = contenedor.dataset.autocomplete;
        const buscador = contenedor.querySelector("[data-buscador-exclusion]");
        const sugerencias = contenedor.querySelector("[data-sugerencias-exclusion]");
        const estado = contenedor.querySelector("[data-estado-exclusion]");
        const cacheResultados = new Map();
        let temporizador = null;
        let controlador = null;

        const mensajeMinimo = tipo === "amid"
            ? `Escribe al menos ${minimoCaracteres} dígitos para buscar.`
            : `Escribe al menos ${minimoCaracteres} caracteres para buscar.`;

        const seleccionarResultado = function (boton) {
            const agregado = crearChip(
                tipo,
                boton.dataset.valor,
                boton.dataset.etiqueta
            );

            if (agregado) {
                buscador.value = "";
                estado.textContent = mensajeMinimo;
                cerrarSugerencias(contenedor, sugerencias);
                buscador.focus();
            }
        };

        const mostrarResultados = function (resultados) {
            const disponibles = resultados.filter(function (resultado) {
                return !estaSeleccionado(tipo, resultado.valor);
            });

            sugerencias.replaceChildren();
            contenedor.dataset.indiceActivo = "-1";

            if (!disponibles.length) {
                estado.textContent = "No hay sugerencias nuevas para esta búsqueda.";
                sugerencias.hidden = true;
                return;
            }

            disponibles.forEach(function (resultado) {
                const boton = document.createElement("button");
                boton.type = "button";
                boton.className = "preferencia-sugerencia";
                boton.dataset.valor = resultado.valor;
                boton.dataset.etiqueta = resultado.etiqueta;
                boton.setAttribute("role", "option");
                boton.setAttribute("aria-selected", "false");
                boton.textContent = resultado.etiqueta;
                sugerencias.appendChild(boton);
            });

            estado.textContent = `${disponibles.length} sugerencia${disponibles.length === 1 ? "" : "s"}.`;
            sugerencias.hidden = false;
        };

        const buscar = async function (termino) {
            if (cacheResultados.has(termino)) {
                mostrarResultados(cacheResultados.get(termino));
                return;
            }

            if (controlador) {
                controlador.abort();
            }

            controlador = new AbortController();
            estado.textContent = "Buscando…";

            const url = new URL(urlSugerencias, window.location.origin);
            url.searchParams.set("tipo", tipo);
            url.searchParams.set("q", termino);

            try {
                const respuesta = await fetch(url, {
                    headers: {"X-Requested-With": "XMLHttpRequest"},
                    signal: controlador.signal,
                });

                if (!respuesta.ok) {
                    throw new Error("No fue posible buscar sugerencias.");
                }

                const datos = await respuesta.json();
                const resultados = Array.isArray(datos.resultados)
                    ? datos.resultados
                    : [];

                cacheResultados.set(termino, resultados);
                mostrarResultados(resultados);
            } catch (error) {
                if (error.name === "AbortError") {
                    return;
                }

                cerrarSugerencias(contenedor, sugerencias);
                estado.textContent = "No fue posible cargar sugerencias. Intenta nuevamente.";
            }
        };

        buscador.addEventListener("input", function () {
            const termino = buscador.value.trim();
            clearTimeout(temporizador);

            if (controlador) {
                controlador.abort();
            }

            cerrarSugerencias(contenedor, sugerencias);

            if (tipo === "amid" && termino && !/^\d+$/.test(termino)) {
                estado.textContent = "Para buscar AMID usa solamente números.";
                return;
            }

            if (termino.length < minimoCaracteres) {
                estado.textContent = mensajeMinimo;
                return;
            }

            estado.textContent = "Preparando búsqueda…";
            temporizador = window.setTimeout(function () {
                buscar(termino);
            }, 300);
        });

        buscador.addEventListener("keydown", function (evento) {
            if (sugerencias.hidden) {
                return;
            }

            const opciones = Array.from(
                sugerencias.querySelectorAll(".preferencia-sugerencia")
            );
            let indice = Number(contenedor.dataset.indiceActivo || -1);

            if (evento.key === "ArrowDown") {
                evento.preventDefault();
                activarSugerencia(contenedor, sugerencias, indice + 1);
            } else if (evento.key === "ArrowUp") {
                evento.preventDefault();
                activarSugerencia(
                    contenedor,
                    sugerencias,
                    indice < 0 ? opciones.length - 1 : indice - 1
                );
            } else if (evento.key === "Enter" && indice >= 0 && opciones[indice]) {
                evento.preventDefault();
                seleccionarResultado(opciones[indice]);
            } else if (evento.key === "Escape") {
                cerrarSugerencias(contenedor, sugerencias);
            }
        });

        sugerencias.addEventListener("mousedown", function (evento) {
            evento.preventDefault();
        });

        sugerencias.addEventListener("click", function (evento) {
            const boton = evento.target.closest(".preferencia-sugerencia");
            if (boton) {
                seleccionarResultado(boton);
            }
        });

        buscador.addEventListener("blur", function () {
            window.setTimeout(function () {
                cerrarSugerencias(contenedor, sugerencias);
            }, 150);
        });
    };

    formulario.querySelectorAll("[data-autocomplete]").forEach(
        inicializarAutocomplete
    );

    formulario.addEventListener("submit", actualizarEstado);
    actualizarEstado();

    const paginaAlertas = document.querySelector(".alertas-page");
    const cacheCaidas = new Map();

    const formatearFechaCaida = function (valor) {
        if (!valor) {
            return "Sin fecha";
        }

        const fecha = new Date(valor);
        if (Number.isNaN(fecha.getTime())) {
            return valor;
        }

        return new Intl.DateTimeFormat("es-CL", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        }).format(fecha);
    };

    const mostrarErrorCaidas = function (contenedor, mensaje) {
        contenedor.replaceChildren();
        const error = document.createElement("p");
        error.className = "detalle-caidas-mensaje detalle-caidas-error";
        error.textContent = mensaje;
        contenedor.appendChild(error);
    };

    const renderizarCaidas = function (contenedor, datos) {
        contenedor.replaceChildren();

        const alertas = Array.isArray(datos.alertas) ? datos.alertas : [];
        if (!alertas.length) {
            const vacio = document.createElement("p");
            vacio.className = "detalle-caidas-mensaje";
            vacio.textContent = "No se encontraron caídas en los últimos 14 días.";
            contenedor.appendChild(vacio);
            return;
        }

        const meta = document.createElement("p");
        meta.className = "detalle-caidas-meta";
        meta.textContent = `${alertas.length} caída${alertas.length === 1 ? "" : "s"} `
            + `confirmada${alertas.length === 1 ? "" : "s"} por Oracle en 14 días`;
        contenedor.appendChild(meta);

        const lista = document.createElement("ol");
        lista.className = "detalle-caidas-lista";

        alertas.forEach(function (alerta) {
            const item = document.createElement("li");
            item.className = "detalle-caida-item";

            const valores = document.createElement("div");
            valores.className = "detalle-caida-valores";

            const cambio = document.createElement("strong");
            cambio.textContent = `${alerta.bateria_anterior}% → ${alerta.bateria_actual}%`;
            valores.appendChild(cambio);

            const magnitud = document.createElement("span");
            magnitud.textContent = `−${alerta.caida} puntos`;
            valores.appendChild(magnitud);

            const fecha = document.createElement("div");
            fecha.className = "detalle-caida-fecha";
            fecha.textContent = `${formatearFechaCaida(alerta.fecha_anterior)} a `
                + `${formatearFechaCaida(alerta.fecha_hora)} · ${alerta.tiempo_transcurrido}`;

            item.appendChild(valores);
            item.appendChild(fecha);
            lista.appendChild(item);
        });

        contenedor.appendChild(lista);
    };

    if (paginaAlertas && paginaAlertas.dataset.caidasUrl) {
        paginaAlertas.addEventListener("click", async function (evento) {
            const boton = evento.target.closest("[data-ver-caidas]");
            if (!boton) {
                return;
            }

            const amid = boton.dataset.amid;
            const contenedor = paginaAlertas.querySelector(
                `[data-detalle-caidas="${amid}"]`
            );
            if (!contenedor) {
                return;
            }

            if (!contenedor.hidden) {
                contenedor.hidden = true;
                boton.setAttribute("aria-expanded", "false");
                boton.textContent = "Ver todas las caídas";
                return;
            }

            contenedor.hidden = false;
            boton.setAttribute("aria-expanded", "true");
            boton.textContent = "Ocultar caídas";

            if (cacheCaidas.has(amid)) {
                renderizarCaidas(contenedor, cacheCaidas.get(amid));
                return;
            }

            contenedor.innerHTML = '<p class="detalle-caidas-mensaje">Cargando caídas…</p>';
            const url = new URL(paginaAlertas.dataset.caidasUrl, window.location.origin);
            url.searchParams.set("amid", amid);

            try {
                const respuesta = await fetch(url, {
                    headers: {"X-Requested-With": "XMLHttpRequest"},
                });
                const datos = await respuesta.json();
                if (!respuesta.ok) {
                    throw new Error(datos.detalle || "No fue posible cargar las caídas.");
                }

                cacheCaidas.set(amid, datos);
                renderizarCaidas(contenedor, datos);
            } catch (error) {
                mostrarErrorCaidas(
                    contenedor,
                    error.message || "No fue posible cargar las caídas."
                );
            }
        });
    }
});