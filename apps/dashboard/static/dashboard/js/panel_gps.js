document.addEventListener("DOMContentLoaded", function () {
    configurarFormularioGps();
    inicializarMapaGps();
});

function obtenerFechaHoyTexto() {
    const hoy = new Date();
    const anio = hoy.getFullYear();
    const mes = String(hoy.getMonth() + 1).padStart(2, "0");
    const dia = String(hoy.getDate()).padStart(2, "0");

    return `${anio}-${mes}-${dia}`;
}

function configurarFormularioGps() {
    const formulario = document.querySelector(".gps-formulario");

    if (!formulario) {
        return;
    }

    const inputAmid = formulario.querySelector('input[name="amid"]');
    const inputFechaDesde = formulario.querySelector('input[name="fecha_desde"]');
    const inputFechaHasta = formulario.querySelector('input[name="fecha_hasta"]');
    const inputHoraDesde = formulario.querySelector('select[name="hora_desde"]');
    const inputHoraHasta = formulario.querySelector('select[name="hora_hasta"]');
    const inputRangoManual = formulario.querySelector('input[name="rango_manual"]');
    const inputHorarioZp = formulario.querySelector('input[name="horario_zp"]');
    const botonHorarioZp = document.querySelector("[data-horario-zp-toggle]");

    let usuarioCambioRango = false;

    function marcarRangoManual() {
        usuarioCambioRango = true;

        if (inputRangoManual) {
            inputRangoManual.value = "1";
        }
    }

    if (inputFechaDesde) {
        inputFechaDesde.addEventListener("change", marcarRangoManual);
    }

    if (inputFechaHasta) {
        inputFechaHasta.addEventListener("change", marcarRangoManual);
    }

    if (inputHoraDesde) {
        inputHoraDesde.addEventListener("change", marcarRangoManual);
    }

    if (inputHoraHasta) {
        inputHoraHasta.addEventListener("change", marcarRangoManual);
    }

    if (botonHorarioZp && inputHorarioZp) {
        botonHorarioZp.addEventListener("click", function () {
            usuarioCambioRango = true;
            inputHorarioZp.value = inputHorarioZp.value === "1" ? "0" : "1";
            formulario.requestSubmit();
        });
    }

    formulario.addEventListener("submit", function () {
        const amidActual = inputAmid ? inputAmid.value.trim() : "";

        if (!amidActual) {
            return;
        }

        /*
            Regla:
            - Si el usuario NO tocó fecha/hora en esta carga de página,
              siempre volvemos a consultar hoy.
            - Si el usuario SÍ tocó fecha/hora, respetamos su rango manual.
        */
        if (!usuarioCambioRango) {
            const hoyTexto = obtenerFechaHoyTexto();

            if (inputFechaDesde) {
                inputFechaDesde.value = hoyTexto;
            }

            if (inputFechaHasta) {
                inputFechaHasta.value = hoyTexto;
            }

            if (inputHoraDesde) {
                inputHoraDesde.value = "00:00";
            }

            if (inputHoraHasta) {
                inputHoraHasta.value = "23:30";
            }

            if (inputRangoManual) {
                inputRangoManual.value = "0";
            }
        }
    });
}

function inicializarMapaGps() {
    const mapaElemento = document.getElementById("mapa-gps");

    if (!mapaElemento) {
        return;
    }

    const latitudElemento = document.getElementById("gps-latitud");
    const longitudElemento = document.getElementById("gps-longitud");
    const amidElemento = document.getElementById("gps-amid");
    const ubicacionesElemento = document.getElementById("gps-ubicaciones");
    const historialElemento = document.getElementById("gps-historial-registros");
    const ubicacionEsperadaElemento = document.getElementById("gps-ubicacion-esperada");

    const ubicacionLaboratorio = {
        nombre: "Laboratorio Zonas Pagas",
        latitud: -33.437191,
        longitud: -70.656102,
        radio_metros: 150
    };

    const latitud = latitudElemento ? JSON.parse(latitudElemento.textContent) : null;
    const longitud = longitudElemento ? JSON.parse(longitudElemento.textContent) : null;
    const amid = amidElemento ? JSON.parse(amidElemento.textContent) : "";
    const ubicaciones = ubicacionesElemento ? JSON.parse(ubicacionesElemento.textContent) : [];
    const registrosHistorial = historialElemento ? JSON.parse(historialElemento.textContent) : [];
    const ubicacionEsperada = ubicacionEsperadaElemento ? JSON.parse(ubicacionEsperadaElemento.textContent) : null;

    const tieneCoordenadas = latitud !== null && longitud !== null;

    const centroInicial = tieneCoordenadas
        ? [latitud, longitud]
        : [-33.4489, -70.6693];

    const zoomInicial = tieneCoordenadas ? 17 : 11;

    const mapa = L.map("mapa-gps").setView(centroInicial, zoomInicial);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
    }).addTo(mapa);

    function moverMapaAUbicacion(ubicacion, zoom = 17) {
        if (!ubicacion || ubicacion.latitud === null || ubicacion.longitud === null) {
            return;
        }

        mapa.setView([ubicacion.latitud, ubicacion.longitud], zoom);
    }

    const puntosRuta = [];
    const marcadoresGps = [];

    if (ubicaciones && ubicaciones.length > 0) {
        ubicaciones.forEach(function (ubicacion, index) {
            const esUltima = index === ubicaciones.length - 1;

            const lat = ubicacion.latitud;
            const lon = ubicacion.longitud;

            const esCoordenadaCero = ubicacion.coordenada_cero === true;

            if (!esCoordenadaCero) {
                puntosRuta.push([lat, lon]);
            }

            let colorPunto = "#9ca3af";
            let radioPunto = 5;

            if (esCoordenadaCero) {
                colorPunto = "#dc2626";
                radioPunto = 7;
            } else if (esUltima) {
                colorPunto = "#2563eb";
                radioPunto = 8;
            }

            const marcador = L.circleMarker([lat, lon], {
                radius: radioPunto,
                color: colorPunto,
                fillColor: colorPunto,
                fillOpacity: esUltima ? 0.9 : 0.55,
                weight: esUltima ? 3 : 2,
            }).addTo(mapa);

            marcadoresGps[index] = marcador;

            const titulo = esUltima ? "Última ubicación" : "Ubicación anterior";

            const estadoRadio = ubicacion.dentro_radio === true
                ? "Dentro del radio"
                : ubicacion.dentro_radio === false
                    ? "Fuera del radio"
                    : "-";

            const avisoCoordenada = esCoordenadaCero
                ? "<br><strong>Advertencia:</strong> coordenada 0,0 reportada por el validador"
                : "";

            marcador.bindPopup(`
                <strong>${titulo}</strong><br>
                AMID: ${amid}<br>
                Hora del bloque: ${ubicacion.fecha_registro || "-"}<br>
                Hora del validador: ${ubicacion.fecha_hora_validador || "-"}<br>
                Latitud: ${lat}<br>
                Longitud: ${lon}<br>
                Batería: ${ubicacion.porcentaje_bateria ?? "-"}%<br>
                Distancia esperada: ${ubicacion.distancia_metros ?? "-"} m<br>
                Estado: ${estadoRadio}
                ${avisoCoordenada}
            `);

            if (esUltima && !esCoordenadaCero) {
                marcador.openPopup();
            }
        });
    }

    if (puntosRuta.length > 1) {
        L.polyline(puntosRuta, {
            color: "#6b7280",
            weight: 3,
            opacity: 0.7,
            dashArray: "6, 8",
        }).addTo(mapa);
    }

    if (ubicacionEsperada) {
        const estadoEsperado = ubicacionEsperada.dentro_radio === true
            ? true
            : ubicacionEsperada.dentro_radio === false
                ? false
                : null;

        const colorEsperado = estadoEsperado === true
            ? "#2563eb"
            : estadoEsperado === false
                ? "#dc2626"
                : "#6b7280";

        L.circle([ubicacionEsperada.latitud, ubicacionEsperada.longitud], {
            radius: ubicacionEsperada.radio_metros,
            color: colorEsperado,
            fillColor: colorEsperado,
            fillOpacity: 0.12,
            weight: 2,
        }).addTo(mapa);

        L.circleMarker([ubicacionEsperada.latitud, ubicacionEsperada.longitud], {
            radius: 6,
            color: "#111827",
            fillColor: "#ffffff",
            fillOpacity: 1,
            weight: 2,
        })
            .addTo(mapa)
            .bindPopup(`
                <strong>Ubicación esperada</strong><br>
                ${ubicacionEsperada.nombre || "-"}<br>
                Radio: ${ubicacionEsperada.radio_metros} m<br>
                Distancia al GPS real: ${ubicacionEsperada.distancia_metros ?? "-"} m<br>
                Estado: ${estadoEsperado === true
                    ? "Dentro del radio"
                    : estadoEsperado === false
                        ? "Fuera del radio"
                        : "Sin GPS válido"
                }
            `);
    }

    if (ubicacionLaboratorio) {
        L.circle([ubicacionLaboratorio.latitud, ubicacionLaboratorio.longitud], {
            radius: ubicacionLaboratorio.radio_metros,
            color: "#7c3aed",
            fillColor: "#7c3aed",
            fillOpacity: 0.10,
            weight: 2,
        }).addTo(mapa);

        L.circleMarker([ubicacionLaboratorio.latitud, ubicacionLaboratorio.longitud], {
            radius: 6,
            color: "#7c3aed",
            fillColor: "#ffffff",
            fillOpacity: 1,
            weight: 2,
        })
            .addTo(mapa)
            .bindPopup(`
                <strong>Laboratorio Zonas Pagas</strong><br>
                ${ubicacionLaboratorio.nombre || "-"}<br>
                Radio: ${ubicacionLaboratorio.radio_metros} m
            `);
    }

    const btnMostrarLaboratorio = document.getElementById("btn-mostrar-laboratorio");
    const btnMostrarEsperada = document.getElementById("btn-mostrar-esperada");

    if (btnMostrarLaboratorio) {
        btnMostrarLaboratorio.addEventListener("click", function () {
            const circuloLaboratorio = L.latLng(
                ubicacionLaboratorio.latitud,
                ubicacionLaboratorio.longitud
            );

            mapa.setView(circuloLaboratorio, 17);
        });
    }

    if (btnMostrarEsperada) {
        btnMostrarEsperada.addEventListener("click", function () {
            moverMapaAUbicacion(ubicacionEsperada, 17);
        });
    }
    inicializarHistorialGps({
        registrosHistorial: registrosHistorial,
        mapa: mapa,
        marcadoresGps: marcadoresGps,
        mapaElemento: mapaElemento,
    });
}

const GPS_HISTORIAL_TAMANIO_PAGINA = 25;

function obtenerFirmaUbicacionEsperada(ubicacion) {
    return [
        ubicacion.ubicacion_esperada_nombre || "",
        ubicacion.ubicacion_esperada_latitud ?? "",
        ubicacion.ubicacion_esperada_longitud ?? "",
        ubicacion.ubicacion_esperada_radio_metros ?? "",
    ].join("|");
}

function prepararRegistrosHistorialGps(registrosHistorial) {
    return registrosHistorial.map(function (ubicacion, index) {
        const anterior = index > 0 ? registrosHistorial[index - 1] : null;
        const cambioUbicacion = anterior
            ? obtenerFirmaUbicacionEsperada(anterior) !== obtenerFirmaUbicacionEsperada(ubicacion)
            : false;

        return {
            ubicacion: ubicacion,
            indiceMapa: ubicacion.indice_mapa,
            cambioUbicacion: cambioUbicacion,
            ubicacionAnteriorNombre: anterior ? anterior.ubicacion_esperada_nombre : null,
        };
    }).reverse();
}

function inicializarHistorialGps({registrosHistorial, mapa, marcadoresGps, mapaElemento}) {
    const panel = document.querySelector("[data-gps-historial]");
    const botonMostrar = document.querySelector("[data-gps-mostrar-historial]");

    if (
        !panel
        || !botonMostrar
        || !Array.isArray(registrosHistorial)
        || registrosHistorial.length === 0
    ) {
        return;
    }

    const toggle = panel.querySelector("[data-gps-historial-toggle]");
    const contenido = panel.querySelector("[data-gps-historial-contenido]");
    const cuerpo = panel.querySelector("[data-gps-historial-body]");
    const vacio = panel.querySelector("[data-gps-historial-vacio]");
    const resumen = panel.querySelector("[data-gps-historial-resumen]");
    const paginaTexto = panel.querySelector("[data-gps-historial-pagina]");
    const anteriorBoton = panel.querySelector("[data-gps-historial-anterior]");
    const siguienteBoton = panel.querySelector("[data-gps-historial-siguiente]");
    const filtros = Array.from(panel.querySelectorAll("[data-gps-historial-filtro]"));

    const registros = prepararRegistrosHistorialGps(registrosHistorial);
    let filtroActual = "todos";
    let paginaActual = 1;
    let inicializado = false;

    function registrosFiltrados() {
        return registros.filter(function (registro) {
            const ubicacion = registro.ubicacion;

            if (filtroActual === "dentro") return ubicacion.dentro_radio === true;
            if (filtroActual === "fuera") {
                return ubicacion.dentro_radio === false && ubicacion.coordenada_cero !== true;
            }
            if (filtroActual === "cero") return ubicacion.coordenada_cero === true;
            if (filtroActual === "sin_transmision") return ubicacion.transmitio_gps === false;
            if (filtroActual === "cambios") return registro.cambioUbicacion;
            return true;
        });
    }

    function crearCelda(texto, clase) {
        const celda = document.createElement("td");
        if (clase) celda.className = clase;
        celda.textContent = texto;
        return celda;
    }

    function obtenerEstado(ubicacion) {
        if (ubicacion.transmitio_gps === false) {
            return {texto: "Sin transmisión", clase: "gps-historial-estado--sin-transmision"};
        }
        if (ubicacion.coordenada_cero === true) {
            return {texto: "GPS 0,0", clase: "gps-historial-estado--cero"};
        }
        if (ubicacion.dentro_radio === true) {
            return {texto: "Dentro", clase: "gps-historial-estado--dentro"};
        }
        if (ubicacion.dentro_radio === false) {
            return {texto: "Fuera", clase: "gps-historial-estado--fuera"};
        }
        return {texto: "Sin evaluación", clase: "gps-historial-estado--neutro"};
    }

    function activarPunto(registro) {
        const ubicacion = registro.ubicacion;
        const marcador = marcadoresGps[registro.indiceMapa];

        if (!marcador || ubicacion.transmitio_gps === false || ubicacion.coordenada_cero === true) return;

        mapa.setView([ubicacion.latitud, ubicacion.longitud], 17);
        marcador.openPopup();
        mapaElemento.scrollIntoView({behavior: "smooth", block: "center"});
    }

    function crearFila(registro) {
        const ubicacion = registro.ubicacion;
        const fila = document.createElement("tr");
        const tieneCoordenadas = ubicacion.latitud !== null
            && ubicacion.latitud !== undefined
            && ubicacion.longitud !== null
            && ubicacion.longitud !== undefined;
        const coordenadas = ubicacion.transmitio_gps === false || !tieneCoordenadas
            ? "—"
            : ubicacion.coordenada_cero === true
                ? "0, 0"
                : `${ubicacion.latitud}, ${ubicacion.longitud}`;
        const distancia = ubicacion.distancia_metros === null
            || ubicacion.distancia_metros === undefined
            ? "—"
            : `${ubicacion.distancia_metros} m`;
        const bateria = ubicacion.porcentaje_bateria === null
            || ubicacion.porcentaje_bateria === undefined
            ? "—"
            : `${ubicacion.porcentaje_bateria}%`;

        const celdaFecha = document.createElement("td");
        celdaFecha.className = "gps-historial-fecha";
        const fechaBloque = document.createElement("strong");
        fechaBloque.textContent = ubicacion.fecha_registro || "—";
        celdaFecha.appendChild(fechaBloque);

        const fechaValidador = document.createElement("small");
        fechaValidador.textContent = ubicacion.fecha_hora_validador
            ? `Validador: ${ubicacion.fecha_hora_validador}`
            : "Validador: sin fecha";
        celdaFecha.appendChild(fechaValidador);

        if (ubicacion.transmitio_gps === false) {
            const horaRepetida = document.createElement("small");
            horaRepetida.className = "gps-historial-hora-repetida";
            horaRepetida.textContent = "Hora repetida: no hubo transmisión nueva";
            celdaFecha.appendChild(horaRepetida);
        }

        fila.appendChild(celdaFecha);
        fila.appendChild(crearCelda(coordenadas, "gps-historial-coordenadas"));

        const celdaEsperada = document.createElement("td");
        const nombreEsperado = document.createElement("strong");
        nombreEsperado.textContent = ubicacion.ubicacion_esperada_nombre || "Sin ubicación esperada";
        celdaEsperada.appendChild(nombreEsperado);

        if (ubicacion.ubicacion_esperada_version) {
            const version = document.createElement("small");
            version.className = "gps-historial-version";
            version.textContent = `Versión ZP: ${ubicacion.ubicacion_esperada_version}`;
            celdaEsperada.appendChild(version);
        }

        if (registro.cambioUbicacion) {
            const cambio = document.createElement("small");
            cambio.className = "gps-historial-cambio";
            cambio.textContent = `Cambió desde ${registro.ubicacionAnteriorNombre || "sin ubicación esperada"}`;
            celdaEsperada.appendChild(cambio);
        }

        fila.appendChild(celdaEsperada);
        fila.appendChild(crearCelda(distancia, "gps-historial-distancia"));
        fila.appendChild(crearCelda(bateria, "gps-historial-bateria"));

        const estado = obtenerEstado(ubicacion);
        const celdaEstado = document.createElement("td");
        const badgeEstado = document.createElement("span");
        badgeEstado.className = `gps-historial-estado ${estado.clase}`;
        badgeEstado.textContent = estado.texto;
        celdaEstado.appendChild(badgeEstado);
        fila.appendChild(celdaEstado);

        if (ubicacion.transmitio_gps !== false && tieneCoordenadas && ubicacion.coordenada_cero !== true) {
            fila.classList.add("is-clickable");
            fila.tabIndex = 0;
            fila.setAttribute("role", "button");
            fila.title = "Mostrar este punto en el mapa";
            fila.addEventListener("click", function () { activarPunto(registro); });
            fila.addEventListener("keydown", function (event) {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    activarPunto(registro);
                }
            });
        }

        return fila;
    }

    function renderizar() {
        const filtrados = registrosFiltrados();
        const totalPaginas = Math.max(1, Math.ceil(filtrados.length / GPS_HISTORIAL_TAMANIO_PAGINA));
        paginaActual = Math.min(paginaActual, totalPaginas);
        const inicio = (paginaActual - 1) * GPS_HISTORIAL_TAMANIO_PAGINA;
        const pagina = filtrados.slice(inicio, inicio + GPS_HISTORIAL_TAMANIO_PAGINA);

        cuerpo.replaceChildren();
        pagina.forEach(function (registro) {
            cuerpo.appendChild(crearFila(registro));
        });

        vacio.hidden = filtrados.length > 0;
        resumen.textContent = filtrados.length === 1
            ? "1 registro"
            : `${filtrados.length} registros`;
        paginaTexto.textContent = `Página ${paginaActual} de ${totalPaginas}`;
        anteriorBoton.disabled = paginaActual <= 1;
        siguienteBoton.disabled = paginaActual >= totalPaginas;
    }

    function establecerHistorialAbierto(abierto) {
        contenido.hidden = !abierto;
        panel.classList.toggle("is-open", abierto);
        toggle.setAttribute("aria-expanded", String(abierto));
        botonMostrar.setAttribute("aria-expanded", String(abierto));

        if (abierto && !inicializado) {
            inicializado = true;
            renderizar();
        }
    }

    function mostrarHistorial(event) {
        if (event) {
            event.preventDefault();
        }

        establecerHistorialAbierto(true);

        window.requestAnimationFrame(function () {
            const posicionContenido = contenido.getBoundingClientRect().top + window.scrollY;

            window.scrollTo({
                top: Math.max(0, posicionContenido - 16),
                behavior: "smooth"
            });
        });
    }

    botonMostrar.addEventListener("click", mostrarHistorial);

    toggle.addEventListener("click", function (event) {
        const abierto = toggle.getAttribute("aria-expanded") === "true";

        if (abierto) {
            establecerHistorialAbierto(false);
        } else {
            mostrarHistorial(event);
        }
    });

    if (window.location.hash === "#historial-gps") {
        mostrarHistorial();
    }

    filtros.forEach(function (boton) {
        boton.addEventListener("click", function () {
            filtroActual = boton.dataset.gpsHistorialFiltro;
            paginaActual = 1;
            filtros.forEach(function (item) {
                item.classList.toggle("is-active", item === boton);
                item.setAttribute("aria-pressed", String(item === boton));
            });
            renderizar();
        });
    });

    anteriorBoton.addEventListener("click", function () {
        if (paginaActual > 1) {
            paginaActual -= 1;
            renderizar();
        }
    });

    siguienteBoton.addEventListener("click", function () {
        const totalPaginas = Math.max(
            1,
            Math.ceil(registrosFiltrados().length / GPS_HISTORIAL_TAMANIO_PAGINA)
        );
        if (paginaActual < totalPaginas) {
            paginaActual += 1;
            renderizar();
        }
    });
}
