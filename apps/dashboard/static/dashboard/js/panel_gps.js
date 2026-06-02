document.addEventListener("DOMContentLoaded", function () {
    const mapaElemento = document.getElementById("mapa-gps");

    if (!mapaElemento) {
        return;
    }

    const latitudElemento = document.getElementById("gps-latitud");
    const longitudElemento = document.getElementById("gps-longitud");
    const amidElemento = document.getElementById("gps-amid");

    const latitud = latitudElemento ? JSON.parse(latitudElemento.textContent) : null;
    const longitud = longitudElemento ? JSON.parse(longitudElemento.textContent) : null;
    const amid = amidElemento ? JSON.parse(amidElemento.textContent) : "";

    const tieneCoordenadas = latitud !== null && longitud !== null;

    const centroInicial = tieneCoordenadas
        ? [latitud, longitud]
        : [-33.4489, -70.6693]; // Santiago por defecto

    const zoomInicial = tieneCoordenadas ? 17 : 11;

    const mapa = L.map("mapa-gps").setView(centroInicial, zoomInicial);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
    }).addTo(mapa);

    if (tieneCoordenadas) {
        L.marker([latitud, longitud])
            .addTo(mapa)
            .bindPopup(`
                <strong>AMID ${amid}</strong><br>
                Latitud: ${latitud}<br>
                Longitud: ${longitud}
            `)
            .openPopup();
    }
});