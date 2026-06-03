document.addEventListener("DOMContentLoaded", function () {
    const mapaElemento = document.getElementById("mapa-gps");

    if (!mapaElemento) {
        return;
    }

    const latitudElemento = document.getElementById("gps-latitud");
    const longitudElemento = document.getElementById("gps-longitud");
    const amidElemento = document.getElementById("gps-amid");
    const ubicacionesElemento = document.getElementById("gps-ubicaciones");

    const latitud = latitudElemento ? JSON.parse(latitudElemento.textContent) : null;
    const longitud = longitudElemento ? JSON.parse(longitudElemento.textContent) : null;
    const amid = amidElemento ? JSON.parse(amidElemento.textContent) : "";
    const ubicaciones = ubicacionesElemento ? JSON.parse(ubicacionesElemento.textContent) : [];

    const tieneCoordenadas = latitud !== null && longitud !== null;

    const centroInicial = tieneCoordenadas
        ? [latitud, longitud]
        : [-33.4489, -70.6693];

    const zoomInicial = tieneCoordenadas ? 17 : 11;

    const mapa = L.map("mapa-gps").setView(centroInicial, zoomInicial);

    const ubicacionEsperadaElemento = document.getElementById("gps-ubicacion-esperada");
    const ubicacionEsperada = ubicacionEsperadaElemento
        ? JSON.parse(ubicacionEsperadaElemento.textContent)
        : null;

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
    }).addTo(mapa);

    if (!ubicaciones || ubicaciones.length === 0) {
        return;
    }

    const puntosRuta = [];

    ubicaciones.forEach(function (ubicacion, index) {
        const esUltima = index === ubicaciones.length - 1;

        const lat = ubicacion.latitud;
        const lon = ubicacion.longitud;

        puntosRuta.push([lat, lon]);

        const colorPunto = esUltima ? "#2563eb" : "#9ca3af";
        const radioPunto = esUltima ? 8 : 5;

        const marcador = L.circleMarker([lat, lon], {
            radius: radioPunto,
            color: colorPunto,
            fillColor: colorPunto,
            fillOpacity: esUltima ? 0.9 : 0.55,
            weight: esUltima ? 3 : 2,
        }).addTo(mapa);

        const titulo = esUltima ? "Última ubicación" : "Ubicación anterior";

        marcador.bindPopup(`
            <strong>${titulo}</strong><br>
            AMID: ${amid}<br>
            Fecha/hora: ${ubicacion.fecha_hora || "-"}<br>
            Latitud: ${lat}<br>
            Longitud: ${lon}<br>
            Batería: ${ubicacion.porcentaje_bateria ?? "-"}%
        `);

        if (esUltima) {
            marcador.openPopup();
        }
    });

    if (puntosRuta.length > 1) {
        L.polyline(puntosRuta, {
            color: "#6b7280",
            weight: 3,
            opacity: 0.7,
            dashArray: "6, 8",
        }).addTo(mapa);
    }

    const limites = L.latLngBounds(puntosRuta);

    if (limites.isValid()) {
        mapa.fitBounds(limites, {
            padding: [40, 40],
            maxZoom: 17,
        });
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
                Distancia al GPS real: ${ubicacionEsperada.distancia_metros} m<br>
                Estado: ${ubicacionEsperada.dentro_radio ? "Dentro del radio" : "Fuera del radio"}
            `);
    }
});