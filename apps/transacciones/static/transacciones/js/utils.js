// Formateadores del Monitor de Traspaso C2D.
//
// Todos los números salen de acá y de ningún otro lado, con el formato
// de Chile: miles con punto, decimales con coma. Se usa Intl en vez de
// toLocaleString suelta para que el separador no dependa de cómo esté
// configurado el equipo del usuario.

window.TRX_UTILS = (function () {

    const DIAS = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];
    const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                   "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

    function entero(decimales) {
        return new Intl.NumberFormat("es-CL", {
            minimumFractionDigits: decimales,
            maximumFractionDigits: decimales
        });
    }

    // Miles con punto: 100183 -> "100.183"
    function miles(valor) {
        return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 }).format(valor || 0);
    }

    // Decimales con coma: 83.5 -> "83,5"
    function decimales(valor, digitos) {
        return entero(digitos === undefined ? 1 : digitos).format(valor || 0);
    }

    // Porcentaje: 83.5 -> "83,5 %"
    function porcentaje(valor, digitos) {
        return decimales(valor, digitos) + " %";
    }

    // Cantidad compacta para los KPI grandes: 2400000 -> "2,4 M"
    function compacto(valor) {
        const n = valor || 0;
        if (n >= 1000000) { return entero(1).format(n / 1000000) + " M"; }
        if (n >= 1000) { return entero(1).format(n / 1000) + " mil"; }
        return miles(n);
    }

    // Minutos sueltos: 3.7 -> "3,7 min"
    function minutos(valor) {
        return decimales(valor, 1) + " min";
    }

    // Tiempo de traspaso en minutos: m:ss min si cabe en una hora,
    // h:mm h si la supera. 220 segundos -> "3:40 min"; 359,8 min -> "5:59 h".
    function traspasoMinutos(valorMin) {
        const total = Math.round((valorMin || 0) * 60);
        const h = Math.floor(total / 3600);
        const m = Math.floor((total % 3600) / 60);
        const s = total % 60;
        if (h >= 1) { return h + ":" + dos(m) + " h"; }
        return m + ":" + dos(s) + " min";
    }

    // Máximo del cuadro diario, que va en segundos: 21932 -> "6:05:32"
    function traspasoSegundos(valorSeg) {
        const total = Math.max(0, Math.round(valorSeg || 0));
        const h = Math.floor(total / 3600);
        const m = Math.floor((total % 3600) / 60);
        const s = total % 60;
        return h + ":" + dos(m) + ":" + dos(s);
    }

    function dos(n) {
        return (n < 10 ? "0" : "") + n;
    }

    // Las fechas llegan como "2026-08-27". Se arman con new Date(año, mes, día)
    // en vez de parsear el string porque "2026-08-27" se interpreta como UTC y
    // en Chile corría al día anterior.
    function partes(iso) {
        const trozos = String(iso).split("-");
        return {
            anio: Number(trozos[0]),
            mes: Number(trozos[1]),
            dia: Number(trozos[2])
        };
    }

    function fecha(iso) {
        const p = partes(iso);
        return DIAS[new Date(p.anio, p.mes - 1, p.dia).getDay()] + " " + p.dia;
    }

    function mes(iso) {
        const p = partes(iso);
        return MESES[p.mes - 1] + " " + p.anio;
    }

    function mesCorto(iso) {
        return MESES[partes(iso).mes - 1].slice(0, 3);
    }

    function diaDelMes(iso) {
        return partes(iso).dia;
    }

    // Columna de la semana en el calendario, con la semana empezando en lunes.
    function columnaLunes(iso) {
        const p = partes(iso);
        return (new Date(p.anio, p.mes - 1, p.dia).getDay() + 6) % 7;
    }

    // Rango inclusivo "1–12 de 48"
    function rango(desde, hasta, total) {
        if (total === 0) { return "Sin dispositivos"; }
        return desde + "–" + hasta + " de " + miles(total);
    }

    return {
        miles: miles,
        decimales: decimales,
        porcentaje: porcentaje,
        compacto: compacto,
        minutos: minutos,
        traspasoMinutos: traspasoMinutos,
        traspasoSegundos: traspasoSegundos,
        fecha: fecha,
        mes: mes,
        mesCorto: mesCorto,
        diaDelMes: diaDelMes,
        columnaLunes: columnaLunes,
        rango: rango,
        DIAS: DIAS,
        MESES: MESES
    };
})();