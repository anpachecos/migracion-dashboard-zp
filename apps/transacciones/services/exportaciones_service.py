"""
Exportaciones del módulo de Transacciones.

Interfaz reservada para la descarga XLSX de las tres salidas. En el hito 1 no
existe exportación: las funciones lanzan NotImplementedError a propósito para que
nadie las use por error ni las descubra como operativas.

Cada función debe recibir el dataset YA normalizado por `trx_service`. Jamás
debe reimplementar reglas de clasificación ni recalcular duraciones.

TODO(trx-002): implementar junto con las rutas `/transacciones/*/exportar/`,
reutilizando el patrón de `apps/dashboard/services/exportaciones_service.py`
(openpyxl + `serializar_excel`).
"""

NO_IMPLEMENTADO = (
    "La exportación de transacciones todavía no está disponible. "
    "Se habilitará junto con la validación del dataset contra los Excel."
)


def construir_excel_informe_interno(filas, filtros=None):
    """Informe_ZP_trxC2D_Interno (27-08-2026 / 28-08-2026)."""

    raise NotImplementedError(NO_IMPLEMENTADO)


def construir_excel_mayor_15(filas, filtros=None):
    """Análisis TRX Mayor a 15 min."""

    raise NotImplementedError(NO_IMPLEMENTADO)


def construir_excel_rezagadas(filas, filtros=None):
    """Análisis TRX Rezagadas."""

    raise NotImplementedError(NO_IMPLEMENTADO)


def exportar_disponible():
    """Flag para mostrar u ocultar el botón de descarga en la interfaz."""

    return False


def nombre_archivo_sugerido(titulo, filtros):
    """Nombre de archivo a partir del título y de la fecha del rango."""

    fecha = (filtros or {}).get("fecha_desde_texto") or "sin-fecha"
    slug = str(titulo or "transacciones").strip().lower().replace(" ", "_")

    return f"transacciones_{slug}_{fecha}.xlsx"
