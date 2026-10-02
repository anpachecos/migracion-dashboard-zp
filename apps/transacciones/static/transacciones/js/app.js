// Controlador del Monitor de Traspaso C2D.
//
// Acá vive el estado global y el pegado de eventos. Ningún número se escribe
// en este archivo: las cifras vienen de `TRX_DATA` y los umbrales del `data-
// umbral-corte-min` que inyecta la vista desde `trx_reglas`. El estado se
// refleja en la URL para que una pestaña con filtro se pueda compartir y para
// que el botón "atrás" del navegador funcione.

window.TRX_APP = (function () {

    const u = window.TRX_UTILS;
    const data = window.TRX_DATA;
    const gfx = window.TRX_CHARTS;

    // Umbrales de presentación del calendario. No son reglas de negocio: son
    // las bandas con que se colorea la grilla.
    const META_PCT = 90;
    const BANDA_ALERTA_PCT = 85;

    // Meta de cumplimiento en minutos, para el color de los promedios.
    const META_SLA_MIN = 5;

    const TABS = ["mensual", "diario", "dispositivos", "rezagadas"];

    let raiz = null;
    let umbral = 0;
    let temporizadorBusqueda = null;
    let fichaSolicitada = 0;

    const estado = {
        pestana: 0,
        mes: "2026-08",
        dia: "2026-08-27",
        operador: "",
        tipo: "",
        lista: { filtro: "all", orden: "avg", dir: "desc", pagina: 0, q: "" },
        validadorAbierto: null
    };

    /* ---------------------------------------------------------
       Utilidades de armado
       --------------------------------------------------------- */

    function el(etiqueta, clase, texto) {
        const nodo = document.createElement(etiqueta);
        if (clase) { nodo.className = clase; }
        if (texto !== undefined && texto !== null) { nodo.textContent = texto; }
        return nodo;
    }

    function zona(nombre) {
        return raiz.querySelector('[data-trx-zona="' + nombre + '"]');
    }

    function nombreMes(iso) {
        return u.MESES[Number(iso.split("-")[1]) - 1];
    }

    function nombreMesCorto(iso) {
        return nombreMes(iso).slice(0, 3);
    }

    function mesAnterior(iso) {
        const p = iso.split("-");
        const anio = Number(p[0]);
        const mes = Number(p[1]) - 1;
        return mes === 0 ? (anio - 1) + "-12" : anio + "-" + (mes < 10 ? "0" : "") + mes;
    }

    function diasDelMes(iso) {
        const p = iso.split("-");
        return new Date(Number(p[0]), Number(p[1]), 0).getDate();
    }

    // Los estados de carga, vacío y error se resuelven siempre acá para que
    // ningún bloque se quede en blanco si algo falla.
    function esqueleto(destino, filas) {
        destino.replaceChildren();
        for (let i = 0; i < (filas || 3); i++) {
            destino.appendChild(el("div", "trx-esqueleto"));
        }
    }

    function mensaje(destino, texto, clase) {
        destino.replaceChildren(el("p", "trx-estado mensaje " + (clase || ""), texto));
    }

    function mensajeAccion(destino, texto, clase, etiquetaBoton, alPulsar) {
        const p = el("p", "trx-estado mensaje " + (clase || ""), texto);
        if (etiquetaBoton) {
            const b = el("button", null, etiquetaBoton);
            b.type = "button";
            b.addEventListener("click", alPulsar);
            p.appendChild(b);
        }
        destino.replaceChildren(p);
    }

    function vacioDispositivos(destino) {
        mensajeAccion(destino, "Sin dispositivos para este filtro", "es-vacio",
            "Limpiar filtros", limpiarFiltrosLista);
    }

    function errorBloque(destino, reintentar) {
        mensajeAccion(destino, "No se pudieron cargar los datos.", "es-error",
            "Reintentar", reintentar);
    }

    async function cargarBloque(destino, tarea, alPintar, alEsqueletar) {
        esqueleto(destino, alEsqueletar);
        try {
            const datos = await tarea();
            alPintar(datos);
        } catch (e) {
            errorBloque(destino, function () { cargarBloque(destino, tarea, alPintar, alEsqueletar); });
        }
    }

    /* ---------------------------------------------------------
       KPIs
       --------------------------------------------------------- */

    function pintarKpis(destino, items) {
        destino.className = "trx-kpis";
        destino.replaceChildren.apply(destino, items.map(function (k) {
            const caja = el("div", "trx-kpi " + (k.clase || ""));
            caja.appendChild(el("div", "trx-kpi-etiqueta", k.etiqueta));
            caja.appendChild(el("div", "trx-kpi-valor", k.valor));
            if (k.detalle) {
                caja.appendChild(el("div", "trx-kpi-detalle", k.detalle));
            }
            return caja;
        }));
    }

    /* ---------------------------------------------------------
       Tablas
       --------------------------------------------------------- */

    function encabezado(columnas, ordenActual, dir) {
        const tr = el("tr");
        columnas.forEach(function (c) {
            const th = el("th", c.clase || "");
            th.textContent = c.titulo;
            if (c.clave) {
                th.classList.add("ordenable");
                th.tabIndex = 0;
                th.setAttribute("role", "button");
                if (c.clave === ordenActual) {
                    th.textContent += dir === "asc" ? " ▲" : " ▼";
                }
                th.setAttribute("aria-label",
                    c.titulo + (c.clave === ordenActual ? (dir === "asc" ? ", ordenado ascendente" : ", ordenado descendente") : ", ordenar"));
                th.addEventListener("click", function () { cambiarOrden(c.clave); });
                th.addEventListener("keydown", function (e) {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); cambiarOrden(c.clave); }
                });
            }
            tr.appendChild(th);
        });
        return tr;
    }

    function tablaVacia(cols, mensaje) {
        const tr = el("tr");
        const td = el("td", "es-mu-txt", mensaje);
        td.colSpan = cols;
        tr.appendChild(td);
        return tr;
    }

    // Una celda con su barrita de 8 px antes del número.
    // El ancho va en porcentaje del ancho disponible en la celda, para que la
// barra se acomode al ancho de columna sin tener que conocer los píxeles.
function celdaConBarra(valor, anchoPorc, clase) {
        const td = el("td");
        const barra = el("span", "trx-minibarra " + (clase || ""));
        barra.style.width = anchoPorc + "%";
        barra.setAttribute("aria-hidden", "true");
        td.appendChild(barra);
        td.appendChild(document.createTextNode(valor));
        return td;
    }

    function filaClicable(tr, alPulsar) {
        tr.classList.add("es-fila");
        tr.tabIndex = 0;
        tr.setAttribute("role", "button");
        tr.addEventListener("click", alPulsar);
        tr.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); alPulsar(); }
        });
        return tr;
    }

    /* =========================================================
       Pestaña 1 · Resumen mensual
       ========================================================= */

    function pintarMensual(d) {
        const k = d.kpis;
        const previo = mesAnterior(estado.mes);

        pintarKpis(zona("mensual-kpis"), [
            {
                etiqueta: "Cumplimiento del mes",
                valor: u.porcentaje(k.cumplimiento),
                clase: "es-er",
                detalle: "Meta " + META_PCT + " % · " + k.diasSobreMeta + " de " +
                    k.diasConDatos + " días sobre la meta"
            },
            {
                etiqueta: "Promedio de traspaso",
                valor: u.minutos(k.promedioMin),
                clase: "es-er",
                detalle: "▲ vs " + u.decimales(k.promedioMesAnteriorMin, 1) +
                    " min en " + nombreMes(previo).toLowerCase()
            },
            {
                etiqueta: "Transacciones",
                valor: u.compacto(k.trx),
                detalle: k.diasConDatos + " días con datos"
            },
            {
                etiqueta: "Días críticos",
                valor: u.miles(k.diasCriticos.length),
                clase: "es-er",
                detalle: k.diasCriticos.join(", ") + " " + nombreMesCorto(estado.mes).toLowerCase() +
                    " (incidente)"
            },
            {
                etiqueta: "Trx > " + umbral + " min",
                valor: u.miles(k.trxMayor15),
                clase: "es-wa",
                detalle: u.miles(k.reincidentes) + " dispositivos reincidentes"
            }
        ]);

        pintarCalendario(d.dias);
        pintarEvolucion(d.meses);
        pintarCuadroDiario(d.dias);
    }

    function pintarCalendario(dias) {
        const destino = zona("mensual-calendario");
        const grilla = el("div", "trx-cal-grid");

        ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"].forEach(function (d) {
            grilla.appendChild(el("div", "cal-dia-sem", d));
        });

        const primero = dias.length ? dias[0].fecha : estado.mes + "-01";
        for (let i = 0; i < u.columnaLunes(primero); i++) {
            grilla.appendChild(el("div"));
        }

        const porDia = {};
        dias.forEach(function (d) { porDia[d.fecha] = d; });

        for (let n = 1; n <= diasDelMes(estado.mes); n++) {
            const iso = estado.mes + "-" + (n < 10 ? "0" : "") + n;
            const fila = porDia[iso];
            const celda = el("button", "trx-cal");
            celda.type = "button";

            if (!fila) {
                celda.classList.add("cal-sin");
                celda.appendChild(el("strong", null, String(n)));
                celda.appendChild(el("small", null, "—"));
                celda.setAttribute("title", String(n) + ": sin dato");
                celda.disabled = true;
            } else {
                const pct = fila.cumplimiento;
                celda.classList.add(pct >= META_PCT ? "cal-ok" : (pct >= BANDA_ALERTA_PCT ? "cal-wa" : "cal-er"));
                celda.appendChild(el("strong", null, String(n)));
                celda.appendChild(el("small", null, u.porcentaje(pct)));
                celda.setAttribute("title", u.fecha(iso) + ": " + u.porcentaje(pct) +
                    " de cumplimiento, " + u.miles(fila.trx) + " trx");
                celda.setAttribute("aria-label", u.fecha(iso) + ", cumplimiento " +
                    u.porcentaje(pct) + ". Abrir el detalle del día.");
                celda.addEventListener("click", function () { abrirDia(iso); });
            }
            grilla.appendChild(celda);
        }

        destino.replaceChildren(grilla);
    }

    function pintarEvolucion(meses) {
        gfx.dibujar(zona("mensual-evolucion"), {
            tipo: "linea",
            datos: meses.map(function (m) {
                return {
                    etiqueta: nombreMesCorto(m.mes),
                    barra: m.promedioMin,
                    linea: m.pctIncumplimiento,
                    tenue: m.mes !== estado.mes
                };
            }),
            topeLinea: 20,
            mostrarValores: true,
            formatoBarra: function (v) { return u.decimales(v, 2); },
            aria: "Evolución mensual del promedio de traspaso y del porcentaje de incumplimiento"
        });
    }

    function pintarCuadroDiario(dias) {
        const tabla = zona("mensual-cuadro");
        const cuerpo = el("tbody");

        dias.slice(-7).forEach(function (f) {
            const tr = el("tr");
            tr.appendChild(el("td", null, u.fecha(f.fecha)));
            tr.appendChild(el("td", null, u.traspasoMinutos(f.promedioSeg / 60)));
            tr.appendChild(el("td", null, u.traspasoSegundos(f.maxSeg)));
            tr.appendChild(el("td", null, u.miles(f.trx)));

            const claseBarra = f.cumplimiento >= META_PCT ? "es-ok" : "es-er";
            tr.appendChild(celdaConBarra(u.porcentaje(f.cumplimiento),
                Math.round(f.cumplimiento), claseBarra));
            tr.appendChild(el("td", null, u.porcentaje(f.pctMayor15)));

            filaClicable(tr, function () { abrirDia(f.fecha); });
            cuerpo.appendChild(tr);
        });

        const thead = el("thead");
        thead.appendChild(encabezado([
            { titulo: "Día" },
            { titulo: "Prom." },
            { titulo: "Máx." },
            { titulo: "Trx" },
            { titulo: "% < " + META_SLA_MIN + " min" },
            { titulo: "% > " + umbral + " min" }
        ]));

        tabla.replaceChildren(thead, cuerpo);
    }

    /* =========================================================
       Pestaña 2 · Resumen diario
       ========================================================= */

    function pintarDiario(d) {
        const k = d.kpis;

        pintarKpis(zona("diario-kpis"), [
            {
                etiqueta: "Cumplimiento (< " + META_SLA_MIN + " min)",
                valor: u.porcentaje(k.cumplimiento),
                clase: "es-ok",
                detalle: "▲ +" + u.decimales(k.deltaPP, 1) + " pp vs ayer"
            },
            {
                etiqueta: "Promedio de traspaso",
                valor: u.traspasoMinutos(k.promedioSeg / 60),
                clase: "es-ok",
                detalle: "≈ igual a ayer"
            },
            {
                etiqueta: "Atraso máximo",
                valor: u.traspasoSegundos(k.maxSeg),
                clase: "es-er",
                detalle: k.maxDetalle
            },
            {
                etiqueta: "Transacciones",
                valor: u.miles(k.trx),
                detalle: u.miles(k.trxSobre5) + " sobre " + META_SLA_MIN + " min"
            },
            {
                etiqueta: "Dispositivos fuera de SLA",
                valor: u.miles(k.dispFueraSLA),
                clase: "es-wa",
                detalle: "de " + u.miles(k.dispTotal) + " (" +
                    u.porcentaje((k.dispFueraSLA / k.dispTotal) * 100) + ")"
            }
        ]);

        gfx.dibujar(zona("diario-hora"), {
            datos: d.porHora.map(function (h) {
                return {
                    etiqueta: String(h.hora),
                    valor: h.promedioMin,
                    color: h.promedioMin > META_SLA_MIN ? "er" : (h.promedioMin > 4 ? "wa" : "ok")
                };
            }),
            umbral: META_SLA_MIN,
            aria: "Tiempo de traspaso por hora de llegada"
        });

        pintarSeveridad(d);
        pintarCalor(d);
        pintarTop(d.top);
    }

    function pintarSeveridad(d) {
        const s = d.severidad;
        const tramos = [
            { clave: "ok", cantidad: s.ok, clase: "seg-ok", etiqueta: "< " + META_SLA_MIN + " min" },
            { clave: "1", cantidad: s.atencion, clase: "seg-1", etiqueta: META_SLA_MIN + "–" + umbral },
            { clave: "2", cantidad: s.alto, clase: "seg-2", etiqueta: umbral + "–30" },
            { clave: "3", cantidad: s.critico, clase: "seg-3", etiqueta: "> 30" }
        ];

        zona("diario-severidad-sub").textContent = u.miles(d.kpis.dispTotal) +
            " dispositivos por severidad de su promedio del día. Clic en un tramo para listar solo esos.";

        const barra = el("div", "trx-segmentos");
        tramos.forEach(function (t) {
            const b = el("button", t.clase, u.miles(t.cantidad));
            b.type = "button";
            b.style.flex = Math.max(t.cantidad, 40) + " 1 0";
            b.setAttribute("title", t.etiqueta + " min: " + u.miles(t.cantidad) + " dispositivos");
            b.setAttribute("aria-label", t.etiqueta + " min, " + u.miles(t.cantidad) +
                " dispositivos. Ver solo estos en la pestaña Dispositivos.");
            b.addEventListener("click", function () {
                estado.lista.filtro = "bad";
                estado.lista.pagina = 0;
                irADispositivos();
            });
            barra.appendChild(b);
        });

        const leyenda = el("div", "trx-leyenda");
        tramos.forEach(function (t) {
            const item = el("span");
            const color = el("i", t.clase);
            item.appendChild(color);
            item.appendChild(document.createTextNode(t.etiqueta + " min"));
            leyenda.appendChild(item);
        });

        zona("diario-severidad").replaceChildren(barra, leyenda);
    }

    function pintarCalor(d) {
        const destino = zona("diario-calor");

        zona("diario-calor-sub").textContent = "Resumen agregado: " +
            d.operadorHora.length + " filas en vez de " + u.miles(1000) + ".";

        const grilla = el("div", "trx-heat");
        grilla.appendChild(el("div"));

        const primeraHora = d.porHora.length ? d.porHora[0].hora : 0;
        for (let h = primeraHora; h < primeraHora + 18; h++) {
            grilla.appendChild(el("div", "heat-hs", String(h)));
        }

        d.operadorHora.forEach(function (fila) {
            const nombre = el("div", "heat-op", fila.operador);
            nombre.title = fila.operador;
            grilla.appendChild(nombre);

            for (let h = primeraHora; h < primeraHora + 18; h++) {
                const punto = fila.horas.filter(function (x) { return x.hora === h; })[0];
                const v = punto ? punto.promedioMin : null;
                const celda = el("div", "heat-celda");
                if (v !== null) {
                    celda.style.background = v < 4 ? "var(--sev-ok)"
                        : (v < 6 ? "var(--sev-1)" : (v < 10 ? "var(--sev-2)" : "var(--sev-3)"));
                    celda.setAttribute("title", fila.operador + " · " + h + " h: " +
                        u.decimales(v, 2) + " min");
                }
                grilla.appendChild(celda);
            }
        });

        destino.replaceChildren(grilla);
    }

    function pintarTop(top) {
        const tabla = zona("diario-top");
        const thead = el("thead");
        thead.appendChild(encabezado([
            { titulo: "Validador" },
            { titulo: "ZP (código · nombre)" },
            { titulo: "Operador" },
            { titulo: "Prom." }
        ]));

        const cuerpo = el("tbody");
        top.forEach(function (f) {
            const tr = el("tr");
            tr.appendChild(el("td", null, String(f.amid)));
            tr.appendChild(el("td", "texto-largo", f.zp + " · " + f.nombre));
            tr.appendChild(el("td", null, f.operador));

            const clase = f.promedioMin > umbral ? "es-er-txt"
                : (f.promedioMin > META_SLA_MIN ? "es-wa-txt" : "es-ok-txt");
            tr.appendChild(el("td", clase, u.minutos(f.promedioMin)));

            filaClicable(tr, function () { abrirFicha(f.amid); });
            cuerpo.appendChild(tr);
        });

        tabla.replaceChildren(thead, cuerpo);
    }

    /* =========================================================
       Pestaña 3 · Dispositivos
       ========================================================= */

    function pintarDispositivos(d) {
        // La tabla se arma nueva en cada render. El `<table>` que trae el
        // template es solo un punto de apoyo: cuando esta zona muestra el
        // esqueleto o el error, ese nodo ya no existe, y buscarlo por
        // `data-trx-zona` devolvería null.
        const contenedor = zona("disp-tabla-zona");

        if (!d.filas.length) {
            vacioDispositivos(contenedor);
            zona("disp-paginacion").replaceChildren();
            return;
        }

        const tabla = el("table", "trx-tabla");

        const thead = el("thead");
        thead.appendChild(encabezado([
            { titulo: "Validador", clave: "id", clase: "texto-largo" },
            { titulo: "ZP (código · nombre)", clave: "zp", clase: "texto-largo" },
            { titulo: "Operador", clave: "op", clase: "texto-largo" },
            { titulo: "Trx", clave: "trx" },
            { titulo: "Prom. del día", clave: "avg" },
            { titulo: "Días mal portado", clave: "dias" },
            { titulo: "Lab", clave: "lab" }
        ], estado.lista.orden, estado.lista.dir));

        const cuerpo = el("tbody");

        // La barra se mide contra el peor de la página que se está viendo, no
        // contra un tope fijo: así la columna siempre se usa y dos validadores
        // de 30 y de 32 min se ven distintos, en vez de los dos al tope.
        const peor = d.filas.reduce(function (a, f) {
            return Math.max(a, f.promedioMin);
        }, 0);

        d.filas.forEach(function (f) {
            const tr = el("tr");
            if (String(f.amid) === String(estado.validadorAbierto)) {
                tr.classList.add("es-activo");
            }
            tr.appendChild(el("td", null, String(f.amid)));
            tr.appendChild(el("td", "texto-largo", f.zp + " · " + f.nombre));
            tr.appendChild(el("td", "texto-largo", f.operador));
            tr.appendChild(el("td", null, u.miles(f.trx)));

            const clase = f.promedioMin > umbral ? "es-er"
                : (f.promedioMin > META_SLA_MIN ? "es-wa" : "es-ok");
            tr.appendChild(celdaConBarra(u.traspasoMinutos(f.promedioMin),
                peor > 0 ? Math.round((f.promedioMin / peor) * 100) : 0, clase));

            tr.appendChild(el("td", f.diasMalPortado ? null : "es-mu-txt",
                f.diasMalPortado ? String(f.diasMalPortado) : "–"));
            tr.appendChild(el("td", f.enLab ? "es-ok-txt" : "es-mu-txt", f.enLab ? "✔" : "–"));

            filaClicable(tr, function () { abrirFicha(f.amid); });
            cuerpo.appendChild(tr);
        });

        tabla.replaceChildren(thead, cuerpo);
        contenedor.replaceChildren(tabla);
        pintarPaginacion(d);
    }

    function pintarPaginacion(d) {
        const destino = zona("disp-paginacion");
        const tam = window.TRX_CONFIG.TAM_PAGINA;
        const paginas = Math.max(1, Math.ceil(d.total / tam));
        const desde = d.total === 0 ? 0 : d.pagina * tam + 1;
        const hasta = Math.min(d.total, (d.pagina + 1) * tam);

        const texto = el("span", null, u.rango(desde, hasta, d.total) + " · página " +
            (d.pagina + 1) + " de " + paginas);

        const botones = el("div", "trx-paginacion-botones");
        const anterior = el("button", null, "‹");
        anterior.type = "button";
        anterior.setAttribute("aria-label", "Página anterior");
        if (d.pagina === 0) {
            anterior.classList.add("btn-deshabilitado");
            anterior.disabled = true;
        } else {
            anterior.addEventListener("click", function () { irAPagina(d.pagina - 1); });
        }

        const siguiente = el("button", null, "›");
        siguiente.type = "button";
        siguiente.setAttribute("aria-label", "Página siguiente");
        if (d.pagina + 1 >= paginas) {
            siguiente.classList.add("btn-deshabilitado");
            siguiente.disabled = true;
        } else {
            siguiente.addEventListener("click", function () { irAPagina(d.pagina + 1); });
        }

        botones.appendChild(anterior);
        botones.appendChild(siguiente);
        destino.replaceChildren(texto, botones);
    }

    function pintarFicha(ficha) {
        const destino = zona("disp-ficha");
        const c = ficha.cabecera;

        destino.hidden = false;
        destino.replaceChildren();

        const cabecera = el("div", "trx-ficha-cabecera");
        cabecera.appendChild(el("h3", null, "Validador " + c.amid + " · " + c.zp + " " + c.nombre));

        const cerrar = el("button", "trx-cerrar", "Cerrar");
        cerrar.type = "button";
        cerrar.setAttribute("data-trx-cerrar-ficha", "");
        cerrar.addEventListener("click", cerrarFicha);
        cabecera.appendChild(cerrar);
        destino.appendChild(cabecera);

        let sub = c.operador + " · promedio de hoy " + u.traspasoMinutos(c.promedioMin) +
            " · " + c.diasMalPortado + " días mal portado en el mes";
        if (c.enLab) { sub += " · pasó por laboratorio"; }
        destino.appendChild(el("p", "trx-ficha-sub", sub));

        const grafico = el("div");
        destino.appendChild(grafico);
        gfx.dibujar(grafico, {
            datos: ficha.porHora.map(function (h) {
                return {
                    etiqueta: String(h.hora),
                    valor: h.promedioMin,
                    color: h.promedioMin > META_SLA_MIN ? "er" : (h.promedioMin > 4 ? "wa" : "ok")
                };
            }),
            umbral: META_SLA_MIN,
            alto: 140,
            aria: "Tiempo de traspaso por hora del validador " + c.amid
        });

        destino.appendChild(el("h3", null, "Últimos 30 días"));
        const tira = el("div", "trx-tira");
        const maximo = ficha.ultimos30dias.reduce(function (a, d) {
            return Math.max(a, d.promedioMin);
        }, 0);
        ficha.ultimos30dias.forEach(function (d) {
            const barra = el("i");
            const alto = maximo > 0 ? (d.promedioMin / maximo) * 100 : 0;
            barra.style.height = alto + "%";
            barra.style.background = d.promedioMin > umbral ? "var(--er)"
                : (d.promedioMin > META_SLA_MIN ? "var(--wa)" : "var(--ok)");
            barra.title = u.fecha(d.fecha) + ": " + u.minutos(d.promedioMin);
            tira.appendChild(barra);
        });
        destino.appendChild(tira);

        destino.appendChild(el("h3", null, "Bitácora de laboratorio"));
        if (!ficha.laboratorio.length) {
            destino.appendChild(el("p", "trx-vacio", "Sin revisiones de laboratorio"));
        } else {
            const lista = el("ul", "trx-lab");
            ficha.laboratorio.forEach(function (r) {
                const li = el("li");
                li.appendChild(el("b", null, u.fecha(r.fecha)));
                const detalle = el("span");
                detalle.textContent = r.situacion + " · " + r.accion;
                li.appendChild(detalle);
                lista.appendChild(li);
            });
            destino.appendChild(lista);
        }

        if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
            destino.scrollIntoView({ behavior: "smooth", block: "start" });
        } else {
            destino.scrollIntoView({ block: "start" });
        }
    }

    /* =========================================================
       Pestaña 4 · Rezagadas
       ========================================================= */

    function pintarRezagadas(d) {
        pintarKpis(zona("rezagadas-kpis"), [
            {
                etiqueta: "Trx rezagadas (mes)",
                valor: u.miles(d.total),
                clase: "es-wa",
                detalle: "llegan ≥ 1 día después"
            },
            {
                etiqueta: "Mayor rezago",
                valor: u.diaDelMes(d.mayorDia.fecha) + " " +
                    nombreMesCorto(d.mayorDia.fecha).toLowerCase(),
                clase: "es-er",
                detalle: u.miles(d.mayorDia.trx) + " trx"
            },
            {
                etiqueta: "Dispositivos involucrados",
                valor: u.miles(d.dispositivos),
                detalle: "ilustrativo"
            }
        ]);

        gfx.dibujar(zona("rezagadas-grafico"), {
            datos: d.porDiaLlegada.map(function (x) {
                return {
                    etiqueta: String(u.diaDelMes(x.fecha)),
                    valor: x.trx,
                    color: x.trx > 800 ? "er" : "wa"
                };
            }),
            aria: "Transacciones rezagadas por día de llegada"
        });
    }

    /* =========================================================
       Navegación y estado
       ========================================================= */

    function irAPagina(n) {
        estado.lista.pagina = Math.max(0, n);
        escribirUrl();
        cargar();
    }

    function cambiarOrden(clave) {
        if (estado.lista.orden === clave) {
            estado.lista.dir = estado.lista.dir === "desc" ? "asc" : "desc";
        } else {
            estado.lista.orden = clave;
            estado.lista.dir = clave === "zp" || clave === "op" ? "asc" : "desc";
        }
        estado.lista.pagina = 0;
        escribirUrl();
        cargar();
    }

    function limpiarFiltrosLista() {
        estado.lista.q = "";
        estado.lista.filtro = "all";
        estado.lista.pagina = 0;
        const buscador = raiz.querySelector("[data-trx-buscar]");
        if (buscador) { buscador.value = ""; }
        raiz.querySelectorAll("[data-trx-chip]").forEach(function (b) {
            b.setAttribute("aria-pressed", b.dataset.trxChip === "all" ? "true" : "false");
        });
        escribirUrl();
        cargar();
    }

    function abrirDia(iso) {
        estado.dia = iso;
        estado.pestana = 1;
        escribirUrl();
        mostrarPestana();
        cargar();
    }

    function irADispositivos() {
        estado.pestana = 2;
        escribirUrl();
        mostrarPestana();
        cargar();
    }

    function abrirFicha(amid) {
        // La ficha se abre sin tocar la búsqueda: el `amid` viaja en la URL, así
        // que recargar la devuelve. Filtrar la lista acá dejaba la tabla vacía
        // cuando el filtro global no coincidía con el dispositivo elegida.
        estado.validadorAbierto = amid;
        estado.pestana = 2;
        escribirUrl();
        mostrarPestana();
        cargar();
    }

    function cerrarFicha() {
        estado.validadorAbierto = null;
        zona("disp-ficha").hidden = true;
        zona("disp-ficha").replaceChildren();
        escribirUrl();
    }

    function mostrarPestana() {
        raiz.querySelectorAll("[data-trx-tab]").forEach(function (b) {
            b.setAttribute("aria-selected", Number(b.dataset.trxTab) === estado.pestana ? "true" : "false");
        });
        raiz.querySelectorAll("[data-trx-seccion]").forEach(function (s) {
            s.hidden = Number(s.dataset.trxSeccion) !== estado.pestana;
        });
        pintarMigas();
    }

    function pintarMigas() {
        const miga = zona("migas");
        const mesTexto = u.mes(estado.mes);

        if (estado.pestana === 0) {
            const a = el("a", null, "Mes");
            a.href = "?p=0";
            a.addEventListener("click", function (e) { e.preventDefault(); irAPestana(0); });
            miga.replaceChildren(a, document.createTextNode(" › " + mesTexto));
            return;
        }

        const vinculoMes = el("a", null, mesTexto);
        vinculoMes.href = "?p=0";
        vinculoMes.addEventListener("click", function (e) { e.preventDefault(); irAPestana(0); });

        if (estado.pestana === 3) {
            miga.replaceChildren(vinculoMes, document.createTextNode(" › Rezagadas"));
            return;
        }

        const vinculoDia = el("a", null, u.fecha(estado.dia));
        vinculoDia.href = "?p=1&dia=" + estado.dia;
        vinculoDia.addEventListener("click", function (e) { e.preventDefault(); abrirDia(estado.dia); });

        if (estado.pestana === 1) {
            miga.replaceChildren(vinculoMes, document.createTextNode(" › "), vinculoDia);
            return;
        }

        const vinculoDisp = el("a", null, "Dispositivos");
        vinculoDisp.href = "?p=2";
        vinculoDisp.addEventListener("click", function (e) { e.preventDefault(); irAPestana(2); });
        miga.replaceChildren(vinculoMes, document.createTextNode(" › "), vinculoDia,
            document.createTextNode(" › "), vinculoDisp);
    }

    function irAPestana(n) {
        estado.pestana = n;
        escribirUrl();
        mostrarPestana();
        cargar();
    }

    function escribirUrl() {
        const q = new URLSearchParams();
        q.set("p", estado.pestana);
        if (estado.mes) { q.set("mes", estado.mes); }
        if (estado.dia) { q.set("dia", estado.dia); }
        if (estado.operador) { q.set("operador", estado.operador); }
        if (estado.tipo) { q.set("tipo", estado.tipo); }
        if (estado.lista.filtro && estado.lista.filtro !== "all") { q.set("filtro", estado.lista.filtro); }
        if (estado.lista.orden) { q.set("orden", estado.lista.orden); }
        if (estado.lista.dir) { q.set("dir", estado.lista.dir); }
        if (estado.lista.pagina) { q.set("pagina", estado.lista.pagina); }
        if (estado.lista.q) { q.set("q", estado.lista.q); }
        if (estado.validadorAbierto) { q.set("amid", estado.validadorAbierto); }
        window.history.replaceState(null, "", window.location.pathname + "?" + q.toString());
    }

    function leerUrl() {
        const q = new URLSearchParams(window.location.search);

        const p = Number(q.get("p"));
        if (!Number.isNaN(p) && p >= 0 && p <= 3) { estado.pestana = p; }

        if (q.get("mes")) { estado.mes = q.get("mes"); }
        if (q.get("dia")) { estado.dia = q.get("dia"); }
        if (q.get("operador")) { estado.operador = q.get("operador"); }
        if (q.get("tipo")) { estado.tipo = q.get("tipo"); }
        if (q.get("q")) { estado.lista.q = q.get("q"); }
        if (q.get("filtro")) { estado.lista.filtro = q.get("filtro"); }
        if (q.get("orden")) { estado.lista.orden = q.get("orden"); }
        if (q.get("dir")) { estado.lista.dir = q.get("dir"); }
        const pg = Number(q.get("pagina"));
        if (!Number.isNaN(pg) && pg > 0) { estado.lista.pagina = pg; }
        if (q.get("amid")) { estado.validadorAbierto = q.get("amid"); }
    }

    function sincronizarControles() {
        raiz.querySelectorAll("[data-trx-globales]").forEach(function (sel) {
            const nombre = sel.dataset.trxGlobales;
            if (nombre === "mes") { sel.value = estado.mes; }
            if (nombre === "operador") { sel.value = estado.operador; }
            if (nombre === "tipo") { sel.value = estado.tipo; }
        });

        const buscador = raiz.querySelector("[data-trx-buscar]");
        if (buscador) { buscador.value = estado.lista.q; }

        raiz.querySelectorAll("[data-trx-chip]").forEach(function (b) {
            b.setAttribute("aria-pressed", b.dataset.trxChip === estado.lista.filtro ? "true" : "false");
        });

        const critico = raiz.querySelector("[data-trx-chip-crit]");
        if (critico) { critico.textContent = "> " + umbral + " min"; }
    }

    /* =========================================================
       Carga
       ========================================================= */

    function cargar() {
        const comunes = { mes: estado.mes, operador: estado.operador, tipo: estado.tipo };

        if (estado.pestana === 0) {
            cargarBloque(zona("mensual-kpis"), function () {
                return data.getResumenMensual(comunes);
            }, pintarMensual, 5);
        } else if (estado.pestana === 1) {
            cargarBloque(zona("diario-kpis"), function () {
                return data.getResumenDiario(Object.assign({ fecha: estado.dia }, comunes));
            }, pintarDiario, 5);
        } else if (estado.pestana === 2) {
            cargarDispositivos();
        } else {
            cargarBloque(zona("rezagadas-kpis"), function () {
                return data.getRezagadas(comunes);
            }, pintarRezagadas, 3);
        }
    }

    function cargarDispositivos() {
        cargarBloque(zona("disp-tabla-zona"), function () {
            return data.getDispositivos({
                fecha: estado.dia,
                operador: estado.operador,
                tipo: estado.tipo,
                q: estado.lista.q,
                filtro: estado.lista.filtro,
                orden: estado.lista.orden,
                dir: estado.lista.dir,
                pagina: estado.lista.pagina,
                tam: window.TRX_CONFIG.TAM_PAGINA
            });
        }, pintarDispositivos, 6);

        if (estado.validadorAbierto !== null && estado.validadorAbierto !== "") {
            const amid = estado.validadorAbierto;
            fichaSolicitada += 1;
            const marca = fichaSolicitada;
            data.getFichaDispositivo({ amid: amid, fecha: estado.dia }).then(function (ficha) {
                if (marca !== fichaSolicitada) { return; }
                zona("disp-ficha").hidden = true;
                if (ficha) { pintarFicha(ficha); }
            }).catch(function () {
                zona("disp-ficha").hidden = true;
            });
        } else {
            zona("disp-ficha").hidden = true;
        }
    }

    /* =========================================================
       Arranque
       ========================================================= */

    function conectarEventos() {
        raiz.querySelectorAll("[data-trx-tab]").forEach(function (b) {
            b.addEventListener("click", function () { irAPestana(Number(b.dataset.trxTab)); });
        });

raiz.querySelectorAll("[data-trx-globales]").forEach(function (sel) {
            sel.addEventListener("change", function () {
                const nombre = sel.dataset.trxGlobales;
                // Cambiar de mes saca el día elegido: el día pertenece al mes
                // que estaba marcado y dejarlo daría una fecha inconsistente.
                if (nombre === "mes") { estado.mes = sel.value; estado.dia = ""; }
                if (nombre === "operador") { estado.operador = sel.value; }
                if (nombre === "tipo") { estado.tipo = sel.value; }
                estado.lista.pagina = 0;
                escribirUrl();
                cargar();
            });
        });

        // "Limpiar filtros" solo toca los tres globales. El buscador y los
        // chips son de la pestaña Dispositivos y se limpian aparte.
        const limpiarGlobales = raiz.querySelector("[data-trx-limpiar-globales]");
        if (limpiarGlobales) {
            limpiarGlobales.addEventListener("click", function () {
                estado.operador = "";
                estado.tipo = "";
                if (estado.dia) { estado.mes = estado.dia.slice(0, 7); estado.dia = ""; }
                estado.lista.pagina = 0;
                raiz.querySelectorAll("[data-trx-globales]").forEach(function (sel) {
                    const nombre = sel.dataset.trxGlobales;
                    if (nombre === "mes") { sel.value = estado.mes; }
                    if (nombre === "operador") { sel.value = estado.operador; }
                    if (nombre === "tipo") { sel.value = estado.tipo; }
                });
                escribirUrl();
                cargar();
            });
        }

        raiz.querySelectorAll("[data-trx-chip]").forEach(function (b) {
            b.addEventListener("click", function () {
                estado.lista.filtro = b.dataset.trxChip;
                estado.lista.pagina = 0;
                raiz.querySelectorAll("[data-trx-chip]").forEach(function (otro) {
                    otro.setAttribute("aria-pressed",
                        otro.dataset.trxChip === estado.lista.filtro ? "true" : "false");
                });
                escribirUrl();
                cargar();
            });
        });

        const buscador = raiz.querySelector("[data-trx-buscar]");
        if (buscador) {
            buscador.addEventListener("input", function () {
                const texto = buscador.value;
                if (temporizadorBusqueda) { clearTimeout(temporizadorBusqueda); }
                temporizadorBusqueda = setTimeout(function () {
                    estado.lista.q = texto;
                    estado.lista.pagina = 0;
                    escribirUrl();
                    cargar();
                }, window.TRX_CONFIG.DEBOUNCE_BUSQUEDA_MS);
            });
        }

        const irALista = raiz.querySelector("[data-trx-ir-lista]");
        if (irALista) {
            irALista.addEventListener("click", function () { irADispositivos(); });
        }
    }

    function iniciar() {
        raiz = document.querySelector("[data-trx-raiz]");
        if (!raiz) { return; }

        umbral = Number(raiz.dataset.umbralCorteMin) || 0;
        data.configurar({ umbralCorteMin: umbral });

        leerUrl();
        sincronizarControles();
        conectarEventos();
        mostrarPestana();
        cargar();

        // Si algún día el proyecto gana un tema oscuro, los gráficos se
        // redibujan solos porque leen los tokens en el momento de pintarse.
        const consulta = window.matchMedia("(prefers-color-scheme: dark)");
        if (consulta.addEventListener) {
            consulta.addEventListener("change", function () { gfx.repintarTodo(); });
        }
    }

    return { iniciar: iniciar };
})();