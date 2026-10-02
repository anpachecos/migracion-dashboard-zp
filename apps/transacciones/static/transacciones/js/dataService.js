// Capa de datos del Monitor de Traspaso C2D.
//
// La interfaz nunca pide datos a otro lado: siempre pasa por acá. Hay dos
// proveedores detrás de la misma interfaz, `mock` y `api`, y el que se usa
// lo decide DATA_SOURCE en config.js. Para conectar la base de datos se
// cambia esa línea y no hay que tocar ningún componente.
//
// El proveedor `mock` no se limita a devolver el arreglo: aplica en el
// cliente la misma lógica que haría el servidor, o sea filtrar por operador
// y tipo cuando el dato lo permite, buscar texto, filtrar por chip, ordenar
// y paginar. Por eso los controles pueden pasarle sus parámetros y no tener
// que filtrar nada por su cuenta.

window.TRX_DATA = (function () {

    const cfg = window.TRX_CONFIG;

    // El umbral de corte llega desde la vista, nunca se escribe acá.
    let umbralCorteMin = null;

    // Los otros dos umbrales no son el umbral de corte: son la meta de
    // cumplimiento y la mínima cantidad de días para considerar reincidente.
    const META_SLA_MIN = 5;
    const MIN_DIAS_REINCIDENTE = 5;

    // De qué campo ordena cada clave que manda la tabla.
    const CAMPOS_ORDEN = {
        avg: "promedioMin",
        id: "amid",
        zp: "zp",
        op: "operador",
        trx: "trx",
        dias: "diasMalPortado",
        lab: "enLab"
    };

    function configurar(opciones) {
        if (opciones && opciones.umbralCorteMin) {
            umbralCorteMin = Number(opciones.umbralCorteMin);
        }
    }

    function esperar(ms) {
        return new Promise((resolver) => setTimeout(resolver, ms));
    }

    function clonar(objeto) {
        return JSON.parse(JSON.stringify(objeto));
    }

    // El tipo sale del nombre del punto, que es lo único que trae el dato.
    function tipoDe(fila) {
        if (fila.nombre.indexOf("Intermodal") !== -1) { return "Intermodal"; }
        if (fila.nombre.indexOf("Parada") !== -1) { return "Parada"; }
        return "Fija";
    }

    /* ---------------------------------------------------------
       Proveedor de relleno
       --------------------------------------------------------- */

    function filasFiltradas(params) {
        let filas = window.MOCK.dispositivos.slice();

        if (params.operador) {
            filas = filas.filter((f) => f.operador === params.operador);
        }

        if (params.tipo) {
            filas = filas.filter((f) => tipoDe(f) === params.tipo);
        }

        if (params.q) {
            const q = String(params.q).toLowerCase();
            filas = filas.filter((f) =>
                String(f.amid).indexOf(q) !== -1 ||
                f.zp.toLowerCase().indexOf(q) !== -1 ||
                f.nombre.toLowerCase().indexOf(q) !== -1 ||
                f.operador.toLowerCase().indexOf(q) !== -1
            );
        }

        if (params.filtro === "bad") {
            filas = filas.filter((f) => f.promedioMin > META_SLA_MIN);
        } else if (params.filtro === "crit") {
            if (umbralCorteMin === null) {
                console.error("TRX_DATA: falta configurar el umbral de corte antes de filtrar por 'crit'.");
                return [];
            }
            filas = filas.filter((f) => f.promedioMin > umbralCorteMin);
        } else if (params.filtro === "rec") {
            filas = filas.filter((f) => f.diasMalPortado >= MIN_DIAS_REINCIDENTE);
        } else if (params.filtro === "lab") {
            filas = filas.filter((f) => f.enLab);
        }

        const campo = CAMPOS_ORDEN[params.orden] || "promedioMin";
        const ascendente = params.dir !== "desc";

        filas.sort((a, b) => {
            const va = a[campo];
            const vb = b[campo];
            let cmp;
            if (typeof va === "number" && typeof vb === "number") {
                cmp = va - vb;
            } else {
                cmp = String(va).localeCompare(String(vb), "es");
            }
            return ascendente ? cmp : -cmp;
        });

        return filas;
    }

    const mock = {

        async getResumenMensual() {
            await esperar(cfg.LATENCIA_MOCK_MS);
            return clonar(window.MOCK.resumenMensual);
        },

        async getResumenDiario() {
            await esperar(cfg.LATENCIA_MOCK_MS);
            return clonar(window.MOCK.resumenDiario);
        },

        async getDispositivos(params) {
            await esperar(cfg.LATENCIA_MOCK_MS);
            const todas = filasFiltradas(params);
            const tam = params.tam || cfg.TAM_PAGINA;
            const pagina = params.pagina || 0;
            const desde = pagina * tam;
            return {
                total: todas.length,
                pagina: pagina,
                filas: todas.slice(desde, desde + tam)
            };
        },

        async getFichaDispositivo(params) {
            await esperar(cfg.LATENCIA_MOCK_MS);
            const fila = window.MOCK.dispositivos.filter(
                (f) => String(f.amid) === String(params.amid)
            )[0];

            if (!fila) { return null; }

            return {
                cabecera: {
                    amid: fila.amid,
                    zp: fila.zp,
                    nombre: fila.nombre,
                    operador: fila.operador,
                    promedioMin: fila.promedioMin,
                    diasMalPortado: fila.diasMalPortado,
                    enLab: fila.enLab
                },
                porHora: clonar(window.MOCK.ficha.porHora),
                ultimos30dias: clonar(window.MOCK.ficha.ultimos30dias),
                laboratorio: clonar(window.MOCK.ficha.laboratorio)
            };
        },

        async getRezagadas() {
            await esperar(cfg.LATENCIA_MOCK_MS);
            return clonar(window.MOCK.rezagadas);
        }
    };

    /* ---------------------------------------------------------
       Proveedor de base de datos
       --------------------------------------------------------- */

    async function pedir(ruta, params, claves) {
        const url = new URL(cfg.API_BASE_URL + ruta, window.location.origin);

        claves.forEach((clave) => {
            const valor = params[clave];
            if (valor !== undefined && valor !== null && valor !== "") {
                url.searchParams.set(clave, valor);
            }
        });

        const respuesta = await fetch(url.toString(), {
            headers: { "Accept": "application/json" },
            credentials: "same-origin"
        });

        if (!respuesta.ok) {
            throw new Error("El servicio respondió " + respuesta.status);
        }

        return respuesta.json();
    }

    const api = {
        getResumenMensual: (p) => pedir("resumen-mensual", p, ["mes", "operador", "tipo"]),
        getResumenDiario: (p) => pedir("resumen-diario", p, ["fecha", "operador", "tipo"]),
        getDispositivos: (p) => pedir("dispositivos", p,
            ["fecha", "operador", "tipo", "q", "filtro", "orden", "dir", "pagina", "tam"]),
        getFichaDispositivo: (p) => pedir("dispositivos/" + encodeURIComponent(p.amid), p, ["fecha"]),
        getRezagadas: (p) => pedir("rezagadas", p, ["mes", "operador", "tipo"])
    };

    const proveedor = cfg.DATA_SOURCE === "api" ? api : mock;

    return {
        configurar: configurar,
        origen: cfg.DATA_SOURCE,
        getResumenMensual: (params) => proveedor.getResumenMensual(params || {}),
        getResumenDiario: (params) => proveedor.getResumenDiario(params || {}),
        getDispositivos: (params) => proveedor.getDispositivos(params || {}),
        getFichaDispositivo: (params) => proveedor.getFichaDispositivo(params || {}),
        getRezagadas: (params) => proveedor.getRezagadas(params || {})
    };
})();