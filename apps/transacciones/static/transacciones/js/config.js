// Configuración del Monitor de Traspaso C2D.
//
// El único interruptor entre datos de relleno y base de datos es
// DATA_SOURCE. Para pasar a producción se cambia "mock" por "api" y
// se ajusta API_BASE_URL: ningún componente ni template se toca.

window.TRX_CONFIG = {
    DATA_SOURCE: "mock",
    API_BASE_URL: "/api/transacciones/",
    LATENCIA_MOCK_MS: 300,
    TAM_PAGINA: 12,
    DEBOUNCE_BUSQUEDA_MS: 250
};