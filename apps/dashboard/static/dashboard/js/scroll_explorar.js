document.addEventListener("DOMContentLoaded", function () {
    const boton = document.querySelector("[data-dashboard-scroll-explorar]");

    if (!boton) {
        return;
    }

    let actualizacionPendiente = false;

    function actualizarVisibilidad() {
        const documento = document.documentElement;
        const altoDocumento = Math.max(
            documento.scrollHeight,
            document.body ? document.body.scrollHeight : 0
        );
        const distanciaAlFinal = altoDocumento - (window.scrollY + window.innerHeight);
        const paginaTieneMasContenido = altoDocumento > window.innerHeight + 80;

        boton.hidden = !paginaTieneMasContenido || distanciaAlFinal <= 100;
        actualizacionPendiente = false;
    }

    function solicitarActualizacion() {
        if (actualizacionPendiente) {
            return;
        }

        actualizacionPendiente = true;
        window.requestAnimationFrame(actualizarVisibilidad);
    }

    boton.addEventListener("click", function () {
        window.scrollBy({
            top: Math.max(320, Math.round(window.innerHeight * 0.72)),
            behavior: "smooth"
        });
    });

    window.addEventListener("scroll", solicitarActualizacion, {passive: true});
    window.addEventListener("resize", solicitarActualizacion);

    if (typeof ResizeObserver !== "undefined" && document.body) {
        const observador = new ResizeObserver(solicitarActualizacion);
        observador.observe(document.body);
    }

    actualizarVisibilidad();
});
