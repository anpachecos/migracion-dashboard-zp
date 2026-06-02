console.log("✅ panel_baterias.js cargado correctamente");

document.addEventListener("DOMContentLoaded", function () {
    configurarFiltrosAutomaticos();
    crearGraficoBateriaDia();
    crearGraficoBateriaPeriodo();
});

function configurarFiltrosAutomaticos() {
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
}

function obtenerDatosJsonScript(id) {
    const elemento = document.getElementById(id);

    if (!elemento) {
        console.warn("No se encontró el script JSON:", id);
        return [];
    }

    try {
        return JSON.parse(elemento.textContent);
    } catch (error) {
        console.error("Error leyendo datos del gráfico:", error);
        return [];
    }
}

function crearGraficoBateriaDia() {
    const canvas = document.getElementById("grafico-bateria-dia");

    if (!canvas) {
        console.warn("No se encontró el canvas grafico-bateria-dia");
        return;
    }

    if (typeof Chart === "undefined") {
        console.error("Chart.js no está cargado.");
        return;
    }

    const datos = obtenerDatosJsonScript("datos-grafico-dia");
    console.log("Datos gráfico día:", datos);

    if (!datos || datos.length === 0) {
        return;
    }

    const labels = datos.map(item => item.hora);
    const bateriaReal = datos.map(item => item.bateria_real);
    const bateriaEsperada = datos.map(item => item.bateria_esperada);

    new Chart(canvas, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Batería real",
                    data: bateriaReal,
                    tension: 0.3,
                    spanGaps: true
                },
                {
                    label: "Batería esperada",
                    data: bateriaEsperada,
                    tension: 0.3,
                    borderDash: [6, 6],
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: "index",
                intersect: false
            },
            plugins: {
                legend: {
                    position: "bottom"
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const valor = context.parsed.y;

                            if (valor === null || valor === undefined) {
                                return context.dataset.label + ": sin dato";
                            }

                            return context.dataset.label + ": " + valor + "%";
                        }
                    }
                }
            },
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    title: {
                        display: true,
                        text: "Batería (%)"
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: "Hora"
                    },
                    ticks: {
                        maxRotation: 60,
                        minRotation: 60,
                        autoSkip: true,
                        maxTicksLimit: 16
                    }
                }
            }
        }
    });
}

function crearGraficoBateriaPeriodo() {
    const canvas = document.getElementById("grafico-bateria-periodo");

    if (!canvas) {
        console.warn("No se encontró el canvas grafico-bateria-periodo");
        return;
    }

    if (typeof Chart === "undefined") {
        console.error("Chart.js no está cargado.");
        return;
    }

    const datos = obtenerDatosJsonScript("datos-grafico-periodo");
    console.log("Datos gráfico período:", datos);

    if (!datos || datos.length === 0) {
        return;
    }

    /*
        IMPORTANTE:
        Usamos índices numéricos como labels.
        Así el eje X no recibe textos largos tipo "31-05-2026 00:00".
    */
    const labels = datos.map((item, index) => index);
    const bateriaReal = datos.map(item => item.bateria_real);

    new Chart(canvas, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Batería real",
                    data: bateriaReal,
                    tension: 0.25,
                    spanGaps: true,
                    pointRadius: 1,
                    pointHoverRadius: 5
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: "index",
                intersect: false
            },
            plugins: {
                legend: {
                    position: "bottom"
                },
                tooltip: {
                    callbacks: {
                        title: function (tooltipItems) {
                            const index = tooltipItems[0].dataIndex;
                            const punto = datos[index];

                            if (!punto) {
                                return "";
                            }

                            return punto.fecha + " " + punto.hora;
                        },
                        label: function (context) {
                            const valor = context.parsed.y;

                            if (valor === null || valor === undefined) {
                                return "Batería real: sin dato";
                            }

                            return "Batería real: " + valor + "%";
                        }
                    }
                }
            },
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    title: {
                        display: true,
                        text: "Batería (%)"
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: "Día"
                    },
                    ticks: {
                        autoSkip: false,
                        maxRotation: 45,
                        minRotation: 45,
                        callback: function (value, index) {
                            const puntoActual = datos[index];

                            if (!puntoActual) {
                                return "";
                            }

                            if (index === 0) {
                                return puntoActual.fecha;
                            }

                            const puntoAnterior = datos[index - 1];

                            if (!puntoAnterior) {
                                return puntoActual.fecha;
                            }

                            if (puntoActual.fecha !== puntoAnterior.fecha) {
                                return puntoActual.fecha;
                            }

                            return "";
                        }
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}