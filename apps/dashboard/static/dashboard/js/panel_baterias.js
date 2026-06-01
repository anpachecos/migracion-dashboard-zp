document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("form-filtros-bateria");

    const filtroDias = document.getElementById("dias");
    const filtroHoraInicio = document.getElementById("hora_inicio");
    const filtroHoraFin = document.getElementById("hora_fin");

    if (!form) {
        return;
    }

    function enviarFormularioAutomatico() {
        form.submit();
    }

    if (filtroDias) {
        filtroDias.addEventListener("change", enviarFormularioAutomatico);
    }

    if (filtroHoraInicio) {
        filtroHoraInicio.addEventListener("change", enviarFormularioAutomatico);
    }

    if (filtroHoraFin) {
        filtroHoraFin.addEventListener("change", enviarFormularioAutomatico);
    }
});