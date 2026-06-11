document.addEventListener("DOMContentLoaded", function () {
    const mapaElemento = document.getElementById("mapa-gps");

    if (!mapaElemento) {
        return;
    }

    const latitudElemento = document.getElementById("gps-latitud");
    const longitudElemento = document.getElementById("gps-longitud");
    const amidElemento = document.getElementById("gps-amid");
    const ubicacionesElemento = document.getElementById("gps-ubicaciones");
    const ubicacionEsperadaElemento = document.getElementById("gps-ubicacion-esperada");
    const ubicacionLaboratorio = {
        nombre: "Laboratorio Zonas Pagas",
        latitud: -33.437191,
        longitud: -70.656102,
        radio_metros: 70
    };

    const latitud = latitudElemento ? JSON.parse(latitudElemento.textContent) : null;
    const longitud = longitudElemento ? JSON.parse(longitudElemento.textContent) : null;
    const amid = amidElemento ? JSON.parse(amidElemento.textContent) : "";
    const ubicaciones = ubicacionesElemento ? JSON.parse(ubicacionesElemento.textContent) : [];
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

    if (ubicaciones && ubicaciones.length > 0) {
        ubicaciones.forEach(function (ubicacion, index) {
            const esUltima = index === ubicaciones.length - 1;

            const lat = ubicacion.latitud;
            const lon = ubicacion.longitud;

            const esCoordenadaCero = ubicacion.coordenada_cero === true;

            puntosRuta.push([lat, lon]);

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
                Fecha/hora: ${ubicacion.fecha_hora || "-"}<br>
                Latitud: ${lat}<br>
                Longitud: ${lon}<br>
                Batería: ${ubicacion.porcentaje_bateria ?? "-"}%<br>
                Distancia esperada: ${ubicacion.distancia_metros ?? "-"} m<br>
                Estado: ${estadoRadio}
                ${avisoCoordenada}
            `);

            if (esUltima) {
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
        L.circle([ubicacionEsperada.latitud, ubicacionEsperada.longitud], {
            radius: ubicacionEsperada.radio_metros,
            color: ubicacionEsperada.dentro_radio ? "#2563eb" : "#dc2626",
            fillColor: ubicacionEsperada.dentro_radio ? "#2563eb" : "#dc2626",
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
                Estado: ${ubicacionEsperada.dentro_radio ? "Dentro del radio" : "Fuera del radio"}
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
});