document.addEventListener("DOMContentLoaded", function () {
    configurarFiltrosAutomaticos();
    crearGraficoBateriaHoy();
    crearGraficoBateriaPrincipal();
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
        return [];
    }

    try {
        return JSON.parse(elemento.textContent);
    } catch (error) {
        console.error("Error leyendo datos del gráfico:", error);
        return [];
    }
}

function valorEsNulo(valor) {
    return valor === null || valor === undefined || Number.isNaN(valor);
}

function formatearPorcentaje(valor) {
    if (valorEsNulo(valor)) {
        return "sin dato";
    }

    return valor + "%";
}

function crearGraficoBateriaHoy() {
    const canvas = document.getElementById("grafico-bateria-hoy");

    if (!canvas) {
        return;
    }

    if (typeof Chart === "undefined") {
        console.error("Chart.js no está cargado.");
        return;
    }

    const datos = obtenerDatosJsonScript("datos-grafico-dia");

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
                    spanGaps: true,
                    pointRadius: 3,
                    pointHoverRadius: 6
                },
                {
                    label: "Curva esperada",
                    data: bateriaEsperada,
                    tension: 0.3,
                    borderDash: [6, 6],
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    spanGaps: true
                }
            ]
        },
        options: obtenerOpcionesGraficoHoy()
    });
}

function crearGraficoBateriaPrincipal() {
    const canvas = document.getElementById("grafico-bateria-principal");

    if (!canvas) {
        return;
    }

    if (typeof Chart === "undefined") {
        console.error("Chart.js no está cargado.");
        return;
    }

    crearGraficoModoPeriodo(canvas);
}

function crearGraficoModoPeriodo(canvas) {
    const datos = obtenerDatosJsonScript("datos-grafico-periodo");

    if (!datos || datos.length === 0) {
        return;
    }

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
        options: obtenerOpcionesGraficoPeriodo(datos)
    });
}

function obtenerOpcionesGraficoHoy() {
    return {
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
                        if (!tooltipItems || tooltipItems.length === 0) {
                            return "";
                        }

                        return "Hora " + tooltipItems[0].label;
                    },
                    label: function (context) {
                        const valor = context.parsed.y;

                        if (valorEsNulo(valor)) {
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
                    autoSkip: true,
                    maxTicksLimit: 8,
                    maxRotation: 45,
                    minRotation: 45
                }
            }
        }
    };
}

function obtenerOpcionesGraficoPeriodo(datos) {
    return {
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

                        if (valorEsNulo(valor)) {
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

                        if (!puntoAnterior || puntoActual.fecha !== puntoAnterior.fecha) {
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
    };
}