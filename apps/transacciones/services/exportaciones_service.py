"""XLSX builders used by the persistent background-work queue."""

from io import BytesIO

from django.conf import settings
from openpyxl import Workbook
from openpyxl.styles import Font

from . import trx_reglas, trx_service


HEADERS = (
    ("nid_contexto_opte", "ID TRX"),
    ("fec_trx", "Fecha TRX"),
    ("fec_bd", "Fecha BD"),
    ("duracion_texto", "Duración"),
    ("estado", "Estado"),
    ("amid", "AMID"),
    ("nombre_entidad", "Operador"),
    ("nombre_sitio", "Sitio"),
    ("fec_trx_fecha", "Día TRX"),
    ("fec_bd_fecha", "Día BD"),
)


def _construir_excel(filas, titulo, filtros=None):
    libro = Workbook()
    hoja = libro.active
    hoja.title = titulo[:31]
    hoja.append([etiqueta for _, etiqueta in HEADERS])
    for celda in hoja[1]:
        celda.font = Font(bold=True)

    for fila in filas:
        hoja.append([_valor_excel(fila.get(clave)) for clave, _ in HEADERS])

    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = hoja.dimensions
    for columna in hoja.columns:
        letra = columna[0].column_letter
        hoja.column_dimensions[letra].width = min(
            max(12, max(len(str(celda.value or "")) for celda in columna) + 2),
            32,
        )

    salida = BytesIO()
    libro.save(salida)
    libro.close()
    return salida.getvalue()


def _valor_excel(valor):
    if valor is None:
        return ""
    return valor


def _filas_para_exportar(parametros, tipo):
    filtros = trx_service.obtener_filtros_desde_parametros(parametros)
    base = trx_service.obtener_dataset_base(
        filtros,
        limite_filas=settings.TRX_EXPORT_MAX_FILAS,
    )
    filas = base["dataset"]
    if tipo == "mayor_15":
        filas = [fila for fila in filas if fila["es_mayor_15"]]
    elif tipo == "rezagadas":
        filas = [fila for fila in filas if fila["es_rezagada"]]
    return filas, filtros


def _generar(tipo, titulo, parametros):
    filas, filtros = _filas_para_exportar(parametros, tipo)
    contenido = _construir_excel(filas, titulo, filtros)
    nombre = nombre_archivo_sugerido(titulo, filtros)
    return {"contenido": contenido, "nombre": nombre}


def construir_excel_informe_interno(filas, filtros=None):
    return _construir_excel(filas, "Informe Interno", filtros)


def construir_excel_mayor_15(filas, filtros=None):
    return _construir_excel(filas, trx_reglas.ETIQUETA_ESTADO_UMBRAL, filtros)


def construir_excel_rezagadas(filas, filtros=None):
    return _construir_excel(filas, "Rezagadas", filtros)


def generar_informe_interno(parametros, trabajo=None):
    return _generar("informe_interno", "Informe Interno", parametros)


def generar_mayor_15(parametros, trabajo=None):
    return _generar("mayor_15", trx_reglas.ETIQUETA_ESTADO_UMBRAL, parametros)


def generar_rezagadas(parametros, trabajo=None):
    return _generar("rezagadas", "Rezagadas", parametros)


def exportar_disponible():
    return True


def nombre_archivo_sugerido(titulo, filtros):
    fecha = (filtros or {}).get("fecha_desde_texto") or "sin-fecha"
    slug = str(titulo or "transacciones").strip().lower().replace(" ", "_")
    return f"transacciones_{slug}_{fecha}.xlsx"
