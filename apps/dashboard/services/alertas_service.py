from datetime import datetime, timedelta

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle

ORDEN_PRIORIDAD = {
    "CRITICA": 1,
    "ALTA": 2,
    "ADVERTENCIA": 3,
    "OK": 4,
}

ALERTAS_POR_PAGINA = 10


def normalizar_numero(valor, default=0):
    if valor is None:
        return default
    return valor


def normalizar_texto(valor, default=""):
    if valor is None:
        return default
    return str(valor)


def construir_condicion_problema(problema):
    """Convierte un filtro de problema a una condición SQL compatible con Oracle."""

    if not problema:
        return None

    mapping = {
        "gps_cero_hoy": "GPS_CERO_HOY > 0",
        "gps_historico": "GPS_CERO_HIST > 0",
        "gps_racha": "RACHA_MAX_GPS_CERO > 0",
        "bateria_caida": "CAIDAS_HOY > 0 OR CAIDAS_HIST > 0",
        "bateria_cero": "BATERIA_CERO_HOY > 0 OR BATERIA_CERO_HIST > 0",
        "ambos": "NIVEL_ALERTA_GPS <> 'OK' AND NIVEL_ALERTA_BATERIA <> 'OK'",
    }

    return mapping.get(problema)


def calcular_estado_estatus(ultimo_estatus):
    """Devuelve el estado visual para la celda de último estatus."""

    if ultimo_estatus is None:
        return {
            "estado_estatus": "sin_estatus",
            "texto_estatus": "Sin estatus",
            "clase_estatus": "estatus-sin",
        }

    try:
        ahora = datetime.now()
    except TypeError:
        ahora = datetime.utcnow()

    if ultimo_estatus < ahora - timedelta(hours=1):
        return {
            "estado_estatus": "estatus_antiguo",
            "texto_estatus": "Hace más de 1 hora",
            "clase_estatus": "estatus-antiguo",
        }

    return {
        "estado_estatus": "con_estatus",
        "texto_estatus": "Con estatus",
        "clase_estatus": "estatus-ok",
    }


def _armar_filtros_alertas(amid=None, nivel=None, tipo_alerta=None, problema=None, solo_con_alerta=True):
    filtros = []
    params = {}

    if solo_con_alerta:
        filtros.append("TIENE_ALERTA = 1")

    if amid:
        filtros.append("AMID = :amid")
        params["amid"] = int(amid)

    if nivel:
        filtros.append("NIVEL_ALERTA_GLOBAL = :nivel")
        params["nivel"] = nivel.upper()

    if tipo_alerta == "GPS":
        filtros.append("NIVEL_ALERTA_GPS <> 'OK'")
    elif tipo_alerta == "BATERIA":
        filtros.append("NIVEL_ALERTA_BATERIA <> 'OK'")

    condicion_problema = construir_condicion_problema(problema)
    if condicion_problema:
        filtros.append(f"({condicion_problema})")

    return filtros, params


def contar_alertas_validadores(amid=None, nivel=None, tipo_alerta=None, problema=None, solo_con_alerta=True):
    filtros, params = _armar_filtros_alertas(
        amid=amid,
        nivel=nivel,
        tipo_alerta=tipo_alerta,
        problema=problema,
        solo_con_alerta=solo_con_alerta,
    )

    where_sql = ""
    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    query = f"""
        SELECT COUNT(*)
        FROM USR_LAB.ALERTA_VALIDADOR_RESUMEN
        {where_sql}
    """

    with obtener_conexion_oracle() as connection:
        cursor = connection.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()

    return int(row[0]) if row and row[0] is not None else 0


def obtener_alertas_validadores(
    amid=None,
    nivel=None,
    tipo_alerta=None,
    problema=None,
    solo_con_alerta=True,
    limite=500,
    offset=0,
    ordenar=True,
):
    """
    Lee alertas desde USR_LAB.ALERTA_VALIDADOR_RESUMEN.
    No calcula reglas. Solo consulta la tabla resumen ya calculada por Oracle.
    """

    filtros, params = _armar_filtros_alertas(
        amid=amid,
        nivel=nivel,
        tipo_alerta=tipo_alerta,
        problema=problema,
        solo_con_alerta=solo_con_alerta,
    )

    where_sql = ""
    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    order_sql = ""
    if ordenar:
        order_sql = """
            ORDER BY
                CASE NIVEL_ALERTA_GLOBAL
                    WHEN 'CRITICA' THEN 1
                    WHEN 'ALTA' THEN 2
                    WHEN 'ADVERTENCIA' THEN 3
                    ELSE 4
                END,
                CASE
                    WHEN NIVEL_ALERTA_GPS <> 'OK' AND NIVEL_ALERTA_BATERIA <> 'OK' THEN 1
                    WHEN NIVEL_ALERTA_BATERIA <> 'OK' THEN 2
                    WHEN NIVEL_ALERTA_GPS <> 'OK' THEN 3
                    ELSE 4
                END,
                CASE
                    WHEN ULTIMO_ESTATUS IS NULL THEN 1
                    WHEN ULTIMO_ESTATUS < SYSDATE - (1/24) THEN 2
                    ELSE 3
                END,
                ULTIMO_ESTATUS ASC NULLS FIRST,
                AMID
        """

    query = f"""
        SELECT *
        FROM (
            SELECT
                q.*,
                ROW_NUMBER() OVER ({order_sql}) AS rn
            FROM (
                SELECT
                    AMID,
                    FECHA_HOY,
                    FECHA_INI_HIST,
                    FECHA_FIN_HIST,
                    ULTIMO_ESTATUS,

                    GPS_TOTAL_HOY,
                    GPS_CERO_HOY,
                    GPS_TOTAL_HIST,
                    GPS_CERO_HIST,
                    GPS_CERO_DIAS_HIST,
                    GPS_CERO_PORC_HOY,
                    GPS_CERO_PORC_HIST,
                    ULTIMO_GPS_FECHA,
                    ULTIMO_GPS_ES_CERO,
                    ULTIMA_FECHA_GPS_CERO,
                    RACHA_MAX_GPS_CERO,
                    NIVEL_ALERTA_GPS,
                    MOTIVO_ALERTA_GPS,

                    BATERIA_ACTUAL,
                    ULTIMA_FECHA_BATERIA,
                    CAIDAS_HOY,
                    CAIDAS_HIST,
                    ULTIMA_FECHA_CAIDA,
                    ULTIMA_CAIDA_DESDE,
                    ULTIMA_CAIDA_HASTA,
                    ULTIMA_CAIDA_DIF,
                    CAIDA_MAX_HOY,
                    CAIDA_MAX_HIST,
                    BATERIA_CERO_HOY,
                    BATERIA_CERO_HIST,
                    ULTIMA_FECHA_BAT_CERO,
                    ULT_BLOQUE_BAT_ES_CERO,
                    NIVEL_ALERTA_BATERIA,
                    MOTIVO_ALERTA_BATERIA,

                    NIVEL_ALERTA_GLOBAL,
                    MOTIVO_PRINCIPAL,
                    ACCION_SUGERIDA,
                    TIENE_ALERTA,
                    FECHA_ACTUALIZACION
                FROM USR_LAB.ALERTA_VALIDADOR_RESUMEN
                {where_sql}
            ) q
        )
        WHERE rn BETWEEN :offset + 1 AND :offset + :limite
    """

    params["offset"] = int(offset)
    params["limite"] = int(limite)

    alertas = []

    with obtener_conexion_oracle() as connection:
        cursor = connection.cursor()
        cursor.execute(query, params)

        columnas = [col[0].lower() for col in cursor.description if col and col[0]]

        for row in cursor.fetchall():
            item = dict(zip(columnas, row))

            item["amid"] = normalizar_numero(item.get("amid"))
            item["nivel_alerta_global"] = normalizar_texto(item.get("nivel_alerta_global"), "OK")
            item["nivel_alerta_gps"] = normalizar_texto(item.get("nivel_alerta_gps"), "OK")
            item["nivel_alerta_bateria"] = normalizar_texto(item.get("nivel_alerta_bateria"), "OK")
            item["motivo_principal"] = normalizar_texto(item.get("motivo_principal"), "Sin alertas")
            item["accion_sugerida"] = normalizar_texto(item.get("accion_sugerida"), "Sin acción")

            item["gps_cero_hoy"] = normalizar_numero(item.get("gps_cero_hoy"))
            item["gps_cero_hist"] = normalizar_numero(item.get("gps_cero_hist"))
            item["gps_cero_porc_hist"] = normalizar_numero(item.get("gps_cero_porc_hist"))
            item["ultimo_gps_es_cero"] = normalizar_numero(item.get("ultimo_gps_es_cero"))
            item["racha_max_gps_cero"] = normalizar_numero(item.get("racha_max_gps_cero"))

            item["bateria_actual"] = item.get("bateria_actual")
            item["caidas_hoy"] = normalizar_numero(item.get("caidas_hoy"))
            item["caidas_hist"] = normalizar_numero(item.get("caidas_hist"))
            item["bateria_cero_hoy"] = normalizar_numero(item.get("bateria_cero_hoy"))
            item["bateria_cero_hist"] = normalizar_numero(item.get("bateria_cero_hist"))

            estado_estatus = calcular_estado_estatus(item.get("ultimo_estatus"))
            item.update(estado_estatus)
            ultimo_estatus = item.get("ultimo_estatus")
            item["texto_fecha_estatus"] = (
                ultimo_estatus.strftime("%d-%m-%Y %H:%M")
                if ultimo_estatus is not None
                else "Sin dato"
            )

            alertas.append(item)

    return alertas


def obtener_resumen_alertas():
    """
    Totales para tarjetas superiores del panel.
    """

    query = """
        SELECT
            COUNT(*) AS total_validadores,
            SUM(CASE WHEN TIENE_ALERTA = 1 THEN 1 ELSE 0 END) AS total_alertas,
            SUM(CASE WHEN NIVEL_ALERTA_GLOBAL = 'CRITICA' THEN 1 ELSE 0 END) AS total_criticas,
            SUM(CASE WHEN NIVEL_ALERTA_GLOBAL = 'ALTA' THEN 1 ELSE 0 END) AS total_altas,
            SUM(CASE WHEN NIVEL_ALERTA_GLOBAL = 'ADVERTENCIA' THEN 1 ELSE 0 END) AS total_advertencias,
            SUM(CASE WHEN NIVEL_ALERTA_GPS <> 'OK' THEN 1 ELSE 0 END) AS total_gps,
            SUM(CASE WHEN NIVEL_ALERTA_BATERIA <> 'OK' THEN 1 ELSE 0 END) AS total_bateria,
            MAX(FECHA_ACTUALIZACION) AS ultima_actualizacion
        FROM USR_LAB.ALERTA_VALIDADOR_RESUMEN
    """

    with obtener_conexion_oracle() as connection:
        cursor = connection.cursor()
        cursor.execute(query)
        row = cursor.fetchone()

    if not row:
        return {
            "total_validadores": 0,
            "total_alertas": 0,
            "total_criticas": 0,
            "total_altas": 0,
            "total_advertencias": 0,
            "total_gps": 0,
            "total_bateria": 0,
            "ultima_actualizacion": None,
        }

    return {
        "total_validadores": normalizar_numero(row[0]),
        "total_alertas": normalizar_numero(row[1]),
        "total_criticas": normalizar_numero(row[2]),
        "total_altas": normalizar_numero(row[3]),
        "total_advertencias": normalizar_numero(row[4]),
        "total_gps": normalizar_numero(row[5]),
        "total_bateria": normalizar_numero(row[6]),
        "ultima_actualizacion": row[7],
    }


def obtener_contexto_alertas(request):
    amid = request.GET.get("amid", "").strip()
    nivel = request.GET.get("nivel", "").strip()
    tipo_alerta = request.GET.get("tipo_alerta", "").strip()
    problema = request.GET.get("problema", "").strip()
    mostrar_todos = request.GET.get("mostrar_todos") == "1"
    page = request.GET.get("page", "1").strip()

    try:
        page_num = int(page) if page else 1
    except ValueError:
        page_num = 1

    page_num = max(page_num, 1)

    total_alertas = contar_alertas_validadores(
        amid=amid if amid else None,
        nivel=nivel if nivel else None,
        tipo_alerta=tipo_alerta if tipo_alerta else None,
        problema=problema if problema else None,
        solo_con_alerta=not mostrar_todos,
    )

    offset = (page_num - 1) * ALERTAS_POR_PAGINA
    alertas = obtener_alertas_validadores(
        amid=amid if amid else None,
        nivel=nivel if nivel else None,
        tipo_alerta=tipo_alerta if tipo_alerta else None,
        problema=problema if problema else None,
        solo_con_alerta=not mostrar_todos,
        limite=ALERTAS_POR_PAGINA,
        offset=offset,
        ordenar=True,
    )

    total_paginas = max(1, (total_alertas + ALERTAS_POR_PAGINA - 1) // ALERTAS_POR_PAGINA)
    page_obj = {
        "numero": page_num,
        "total": total_paginas,
        "has_previous": page_num > 1,
        "has_next": page_num < total_paginas,
        "previous_page_number": page_num - 1 if page_num > 1 else None,
        "next_page_number": page_num + 1 if page_num < total_paginas else None,
        "page_range": range(1, total_paginas + 1),
        "start_index": offset + 1,
        "end_index": min(offset + len(alertas), total_alertas),
    }

    resumen = obtener_resumen_alertas()

    query_params = []
    if amid:
        query_params.append(f"amid={amid}")
    if nivel:
        query_params.append(f"nivel={nivel}")
    if tipo_alerta:
        query_params.append(f"tipo_alerta={tipo_alerta}")
    if problema:
        query_params.append(f"problema={problema}")
    if mostrar_todos:
        query_params.append("mostrar_todos=1")

    querystring_sin_page = "&".join(query_params)

    return {
        "alertas": alertas,
        "resumen_alertas": resumen,
        "filtro_amid": amid,
        "filtro_nivel": nivel,
        "filtro_tipo_alerta": tipo_alerta,
        "filtro_problema": problema,
        "mostrar_todos": mostrar_todos,
        "page_obj": page_obj,
        "querystring_sin_page": querystring_sin_page,
        "alertas_por_pagina": ALERTAS_POR_PAGINA,
    }