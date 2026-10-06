// Gráficos de barras en SVG del Monitor de Traspaso C2D.
//
// No hay librerías: el SVG se arma con createElementNS. Los colores se
// leen de los tokens del CSS en el momento de dibujar, nunca se escriben
// acá, así que si mañana se redefine un token el gráfico lo acompanha. Por
// eso además hay un registro de todo lo dibujado: `repintarTodo` vuelve a
// generar cada gráfico cuando cambia el tema.

window.TRX_CHARTS = (function () {

    const NS = "http://www.w3.org/2000/svg";
    const ANCHO = 460;
    const MARGEN_IZQ = 26;
    const ALTO_UTIL = 190 - 36;

    const registry = [];

    function leerTokens(contenedor) {
        const cs = getComputedStyle(contenedor);
        const v = (nombre) => cs.getPropertyValue(nombre).trim();
        return {
            mu: v("--mu"),
            tx: v("--tx"),
            bd: v("--bd"),
            er: v("--er"),
            ac: v("--ac"),
            ok: v("--ok"),
            wa: v("--wa"),
            sevOk: v("--sev-ok"),
            sev1: v("--sev-1"),
            sev2: v("--sev-2"),
            sev3: v("--sev-3"),
            sin: v("--sin")
        };
    }

    function nodo(tipo, atributos) {
        const e = document.createElementNS(NS, tipo);
        for (const clave in atributos) {
            if (atributos[clave] !== undefined && atributos[clave] !== null) {
                e.setAttribute(clave, String(atributos[clave]));
            }
        }
        return e;
    }

    // Colores admitidos por nombre de token. Un color desconocido cae en el
    // acento para que un valor mal escrito no deje la barra invisible.
    function colorDe(tokens, nombre) {
        return tokens[nombre] || tokens.ac;
    }

    function maximoDe(valores) {
        const mayor = valores.reduce((a, b) => (b > a ? b : a), 0);
        return (mayor > 0 ? mayor : 1) * 1.1;
    }

    function anchoDeBarra(cantidad) {
        return (ANCHO - MARGEN_IZQ) / cantidad - 6;
    }

    // Barras simples con una línea punteada opcional de umbral.
    function barras(contenedor, opciones) {
        const tokens = leerTokens(contenedor);
        const datos = opciones.datos || [];
        const alto = opciones.alto || 190;
        const util = alto - 36;
        const tope = maximoDe(datos.map((d) => d.valor));
        const paso = (ANCHO - MARGEN_IZQ) / (datos.length || 1);
        const grosor = anchoDeBarra(datos.length);
        const altoUtil = util;

        const svg = nodo("svg", {
            "class": "trx-gfx",
            viewBox: "0 0 " + ANCHO + " " + alto,
            role: "img",
            "aria-label": opciones.aria || "Gráfico de barras"
        });

        // Línea de base y eje vertical.
        svg.appendChild(nodo("line", {
            x1: MARGEN_IZQ, y1: util, x2: ANCHO, y2: util,
            stroke: tokens.bd || tokens.mu, "stroke-width": 1
        }));

        datos.forEach((d, i) => {
            const x = MARGEN_IZQ + i * paso + 3;
            const h = Math.max(1, (d.valor / tope) * altoUtil);
            const y = util - h;

            svg.appendChild(nodo("rect", {
                x: x, y: y, width: grosor, height: h, rx: 3,
                fill: colorDe(tokens, d.color || "ac")
            }));

            if (opciones.mostrarValores) {
                const texto = nodo("text", {
                    x: x + grosor / 2, y: Math.max(9, y - 4),
                    "text-anchor": "middle", "class": "gfx-etiqueta",
                    fill: tokens.mu
                });
                texto.textContent = opciones.formatoValor ? opciones.formatoValor(d.valor) : d.valor;
                svg.appendChild(texto);
            }

            const etiqueta = nodo("text", {
                x: x + grosor / 2, y: util + 13,
                "text-anchor": "middle", fill: tokens.mu
            });
            etiqueta.textContent = d.etiqueta;
            svg.appendChild(etiqueta);
        });

        if (opciones.umbral !== undefined && opciones.umbral !== null) {
            const y = util - (opciones.umbral / tope) * altoUtil;
            svg.appendChild(nodo("line", {
                x1: MARGEN_IZQ, y1: y, x2: ANCHO, y2: y,
                stroke: tokens.er, "stroke-width": 1.5, "stroke-dasharray": "4 3"
            }));
        }

        contenedor.replaceChildren(svg);
        return svg;
    }

    // Barras para una serie y línea para otra, con escalas separadas.
    // Se usa en la evolución mensual: minutos en las barras y porcentaje
    // de incumplimiento en la línea, que va de 0 a topeLinea.
    function barrasConLinea(contenedor, opciones) {
        const tokens = leerTokens(contenedor);
        const datos = opciones.datos || [];
        const alto = opciones.alto || 190;
        const util = alto - 36;
        const tope = maximoDe(datos.map((d) => d.barra));
        const topeLinea = opciones.topeLinea || 20;
        const paso = (ANCHO - MARGEN_IZQ) / (datos.length || 1);
        const grosor = anchoDeBarra(datos.length);

        const svg = nodo("svg", {
            "class": "trx-gfx",
            viewBox: "0 0 " + ANCHO + " " + alto,
            role: "img",
            "aria-label": opciones.aria || "Gráfico de barras y línea"
        });

        svg.appendChild(nodo("line", {
            x1: MARGEN_IZQ, y1: util, x2: ANCHO, y2: util,
            stroke: tokens.bd || tokens.mu, "stroke-width": 1
        }));

        datos.forEach((d, i) => {
            const x = MARGEN_IZQ + i * paso + 3;
            const h = Math.max(1, (d.barra / tope) * util);
            svg.appendChild(nodo("rect", {
                x: x, y: util - h, width: grosor, height: h, rx: 3,
                fill: colorDe(tokens, d.color || "ac"),
                opacity: d.tenue ? ".55" : "1"
            }));

            if (opciones.mostrarValores) {
                const texto = nodo("text", {
                    x: x + grosor / 2, y: Math.max(9, util - h - 4),
                    "text-anchor": "middle", "class": "gfx-etiqueta", fill: tokens.mu
                });
                texto.textContent = opciones.formatoBarra ? opciones.formatoBarra(d.barra) : d.barra;
                svg.appendChild(texto);
            }

            const etiqueta = nodo("text", {
                x: x + grosor / 2, y: util + 13, "text-anchor": "middle", fill: tokens.mu
            });
            etiqueta.textContent = d.etiqueta;
            svg.appendChild(etiqueta);
        });

        const puntos = datos.map((d, i) => {
            const x = MARGEN_IZQ + i * paso + 3 + grosor / 2;
            const y = util - (d.linea / topeLinea) * util;
            return x + "," + y;
        }).join(" ");

        svg.appendChild(nodo("polyline", {
            points: puntos, fill: "none", stroke: tokens.er,
            "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round"
        }));

        datos.forEach((d, i) => {
            const x = MARGEN_IZQ + i * paso + 3 + grosor / 2;
            const y = util - (d.linea / topeLinea) * util;
            svg.appendChild(nodo("circle", { cx: x, cy: y, r: 2.5, fill: tokens.er }));
        });

        contenedor.replaceChildren(svg);
        return svg;
    }

    function dibujar(contenedor, opciones) {
        if (!contenedor) { return; }
        const item = { contenedor: contenedor, opciones: opciones };
        const i = registry.findIndex((otro) => otro.contenedor === contenedor);
        if (i === -1) { registry.push(item); } else { registry[i] = item; }

        if (opciones.tipo === "linea") {
            barrasConLinea(contenedor, opciones);
        } else {
            barras(contenedor, opciones);
        }
    }

    // Vuelve a dibujar todo lo que ya estaba en pantalla.
    function repintarTodo() {
        registry.forEach((item) => {
            if (item.opciones.tipo === "linea") {
                barrasConLinea(item.contenedor, item.opciones);
            } else {
                barras(item.contenedor, item.opciones);
            }
        });
    }

    function limpiar() {
        registry.length = 0;
    }

    return {
        dibujar: dibujar,
        repintarTodo: repintarTodo,
        limpiar: limpiar
    };
})();