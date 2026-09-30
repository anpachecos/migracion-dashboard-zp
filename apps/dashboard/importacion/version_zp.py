"""Contrato funcional del archivo Version_DB."""

import re

from apps.dashboard.services.normalizacion import normalizar_texto_sin_acentos


VERSION_ZP_EXTENSION = ".xlsx"
VERSION_ZP_SHEET_NAME = "Version_DB"

MAPEO_COLUMNAS_EXCEL = {
    "codigo zp ts": "CODIGO_ZP_TS",
    "cod parada1": "COD_PARADA1",
    "cod parada2": "COD_PARADA2",
    "nombre": "NOMBRE",
    "comuna": "COMUNA",
    "unidad": "UNIDAD",
    "operador": "OPERADOR",
    "un": "UN",
    "u n secundaria 1": "UN_SECUNDARIA_1",
    "u n secundaria 2": "UN_SECUNDARIA_2",
    "u n secundaria 3": "UN_SECUNDARIA_3",
    "pst": "PST",
    "servicios": "SERVICIOS",
    "total val vigentes por zp": "TOTAL_VAL_VIGENTES_ZP",
    "horario": "HORARIO",
    "horario laboral pm": "HORARIO_LABORAL_PM",
    "horario sabado": "HORARIO_SABADO",
    "horario domingo": "HORARIO_DOMINGO",
    "inicio operacion": "INICIO_OPERACION",
    "fin operacion": "FIN_OPERACION",
    "patente": "PATENTE",
    "op id": "OP_ID",
    "bus id": "BUS_ID",
    "serie val": "SERIE_VALIDADOR",
    "idds": "IDDS",
    "n val": "NUM_VAL",
    "latitud": "LATITUD_ESPERADA",
    "longitud": "LONGITUD_ESPERADA",
    "x": "X",
    "y": "Y",
    "operativa": "OPERATIVA",
    "contingencia": "CONTINGENCIA",
    "mixta": "MIXTA",
    "radio": "RADIO_METROS",
    "tipo": "TIPO",
    "renovada": "RENOVADA",
}

COLUMNAS_ESTRUCTURALES_REQUERIDAS = frozenset({
    "NOMBRE",
    "IDDS",
    "OPERATIVA",
    "LATITUD_ESPERADA",
    "LONGITUD_ESPERADA",
    "RADIO_METROS",
})


def normalizar_nombre_columna(valor):
    texto = normalizar_texto_sin_acentos(valor)
    texto = re.sub(r"[^a-z0-9]+", " ", texto)

    return re.sub(r"\s+", " ", texto).strip()


def nombre_columna_oracle(valor):
    return MAPEO_COLUMNAS_EXCEL.get(normalizar_nombre_columna(valor))
