import unicodedata

from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.core.cache import cache

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle

ORDEN_PRIORIDAD = {
    "CRITICA": 1,
    "ALTA": 2,
    "ADVERTENCIA": 3,
    "OK": 4,
}

ALERTAS_POR_PAGINA = 10
CACHE_KEY_RESUMEN_ALERTAS = "dashboard:resumen-alertas-activos:v3"
CACHE_TIMEOUT_RESUMEN_ALERTAS = 60
CACHE_KEY_UBICACIONES_ALERTAS = "dashboard:ubicaciones-alertas:v1"
CACHE_TIMEOUT_UBICACIONES_ALERTAS = 300
UBICACION_SIN_ASIGNAR = "Sin ubicaci\u00f3n asignada"
MIN_CARACTERES_BUSQUEDA_ALERTAS = 2
LIMITE_SUGERENCIAS_ALERTAS = 15
MAX_LIMITE_SUGERENCIAS_ALERTAS = 20


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


def construir_condicion_estatus(estatus):
    """Convierte el filtro de último estatus a una condición SQL."""

    if not estatus:
        return None

    estatus = estatus.upper()

    mapping = {
        # Tiene estatus de hoy y además fue recibido hace una hora o menos.
        "CON_ESTATUS": "ULTIMO_ESTATUS >= TRUNC(SYSDATE) AND ULTIMO_ESTATUS >= SYSDATE - (1/24)",

        # Tiene estatus de hoy, pero el último fue recibido hace más de una hora.
        "ANTIGUO": "ULTIMO_ESTATUS >= TRUNC(SYSDATE) AND ULTIMO_ESTATUS < SYSDATE - (1/24)",

        # No tiene estatus de hoy. Incluye NULL o último estatus de días anteriores.
        "SIN_ESTATUS": "ULTIMO_ESTATUS IS NULL OR ULTIMO_ESTATUS < TRUNC(SYSDATE)",
    }

    return mapping.get(estatus)


def calcular_estado_estatus(ultimo_estatus):
    """
    Devuelve el estado visual para la celda de último estatus.

    Criterios:
    - Con estatus: tiene estatus de hoy y fue recibido hace una hora o menos.
    - Hace más de 1 hora: tiene estatus de hoy, pero fue recibido hace más de una hora.
    - Sin estatus hoy: no tiene estatus o el último estatus no corresponde al día actual.
    """

    if ultimo_estatus is None:
        return {
            "estado_estatus": "sin_estatus",
            "texto_estatus": "Sin estatus hoy",
            "clase_estatus": "estatus-sin",
        }

    ahora = datetime.now()
    inicio_hoy = datetime.combine(ahora.date(), datetime.min.time())

    if ultimo_estatus < inicio_hoy:
        return {
            "estado_estatus": "sin_estatus",
            "texto_estatus": "Sin estatus hoy",
            "clase_estatus": "estatus-sin",
        }

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


def _armar_filtros_alertas(
    amid=None,
    nivel=None,
    tipo_alerta=None,
    problema=None,
    estatus=None,
    solo_con_alerta=True,
    amids_excluidos=None,
    ubicaciones_excluidas=None,
):
    filtros = []
    params = {}

    if solo_con_alerta:
        filtros.append("TIENE_ALERTA = 1")

    if amid:
        filtros.append("r.AMID = :amid")
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

    condicion_estatus = construir_condicion_estatus(estatus)
    if condicion_estatus:
        filtros.append(f"({condicion_estatus})")

    binds_amids = []
    for indice, amid_excluido in enumerate(amids_excluidos or []):
        nombre_bind = f"amid_excluido_{indice}"
        binds_amids.append(f":{nombre_bind}")
        params[nombre_bind] = int(amid_excluido)

    if binds_amids:
        filtros.append(f"r.AMID NOT IN ({', '.join(binds_amids)})")

    binds_ubicaciones = []
    for indice, ubicacion in enumerate(ubicaciones_excluidas or []):
        nombre_bind = f"ubicacion_excluida_{indice}"
        binds_ubicaciones.append(f":{nombre_bind}")
        params[nombre_bind] = str(ubicacion)

    if binds_ubicaciones:
        params["ubicacion_sin_asignar"] = UBICACION_SIN_ASIGNAR
        filtros.append(
            "NVL(TRIM(u.NOMBRE), :ubicacion_sin_asignar) "
            f"NOT IN ({', '.join(binds_ubicaciones)})"
        )

    return filtros, params


def contar_alertas_validadores(
    amid=None,
    nivel=None,
    tipo_alerta=None,
    problema=None,
    estatus=None,
    solo_con_alerta=True,
    amids_excluidos=None,
    ubicaciones_excluidas=None,
):
    filtros, params = _armar_filtros_alertas(
        amid=amid,
        nivel=nivel,
        tipo_alerta=tipo_alerta,
        problema=problema,
        estatus=estatus,
        solo_con_alerta=solo_con_alerta,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )

    where_sql = ""
    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    query = f"""
        SELECT COUNT(*)
        FROM USR_LAB.VW_ALERTA_VALIDADOR_ACTIVA r
        LEFT JOIN USR_LAB.UBICACION_ESPERADA_VALIDADOR u
          ON u.AMID = r.AMID
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
    estatus=None,
    solo_con_alerta=True,
    limite=500,
    offset=0,
    ordenar=True,
    amids_excluidos=None,
    ubicaciones_excluidas=None,
):
    """
    Lee alertas desde USR_LAB.VW_ALERTA_VALIDADOR_ACTIVA.
    No calcula reglas. Solo consulta la tabla resumen ya calculada por Oracle.
    """

    filtros, params = _armar_filtros_alertas(
        amid=amid,
        nivel=nivel,
        tipo_alerta=tipo_alerta,
        problema=problema,
        estatus=estatus,
        solo_con_alerta=solo_con_alerta,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )

    where_sql = ""
    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    order_sql = ""
    if ordenar:
        order_sql = """
            ORDER BY
                CASE
                    WHEN NIVEL_ALERTA_GLOBAL = 'CRITICA'
                     AND NIVEL_ALERTA_GPS = 'CRITICA'
                     AND NIVEL_ALERTA_BATERIA = 'CRITICA' THEN 1

                    WHEN NIVEL_ALERTA_GLOBAL = 'CRITICA'
                     AND NIVEL_ALERTA_GPS = 'CRITICA' THEN 2

                    WHEN NIVEL_ALERTA_GLOBAL = 'CRITICA'
                     AND NIVEL_ALERTA_BATERIA = 'CRITICA' THEN 3

                    WHEN NIVEL_ALERTA_GLOBAL = 'CRITICA' THEN 4

                    WHEN NIVEL_ALERTA_GLOBAL = 'ALTA'
                     AND NIVEL_ALERTA_GPS = 'ALTA'
                     AND NIVEL_ALERTA_BATERIA = 'ALTA' THEN 5

                    WHEN NIVEL_ALERTA_GLOBAL = 'ALTA'
                     AND NIVEL_ALERTA_GPS = 'ALTA' THEN 6

                    WHEN NIVEL_ALERTA_GLOBAL = 'ALTA'
                     AND NIVEL_ALERTA_BATERIA = 'ALTA' THEN 7

                    WHEN NIVEL_ALERTA_GLOBAL = 'ALTA' THEN 8

                    WHEN NIVEL_ALERTA_GLOBAL = 'ADVERTENCIA'
                     AND NIVEL_ALERTA_GPS = 'ADVERTENCIA'
                     AND NIVEL_ALERTA_BATERIA = 'ADVERTENCIA' THEN 9

                    WHEN NIVEL_ALERTA_GLOBAL = 'ADVERTENCIA' THEN 10

                    ELSE 11
                END,
                CASE
                    WHEN ULTIMO_ESTATUS IS NULL OR ULTIMO_ESTATUS < TRUNC(SYSDATE) THEN 1
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
                    r.AMID,
                    NVL(TRIM(u.NOMBRE), :ubicacion_sin_asignar) AS UBICACION_ACTUAL,
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
                FROM USR_LAB.VW_ALERTA_VALIDADOR_ACTIVA r
                LEFT JOIN USR_LAB.UBICACION_ESPERADA_VALIDADOR u
                  ON u.AMID = r.AMID
                {where_sql}
            ) q
        )
        WHERE rn BETWEEN :offset + 1 AND :offset + :limite
    """

    params["offset"] = int(offset)
    params["limite"] = int(limite)
    params["ubicacion_sin_asignar"] = UBICACION_SIN_ASIGNAR

    alertas = []

    with obtener_conexion_oracle() as connection:
        cursor = connection.cursor()
        cursor.execute(query, params)

        columnas = [col[0].lower() for col in cursor.description if col and col[0]]

        for row in cursor.fetchall():
            item = dict(zip(columnas, row))

            item["amid"] = normalizar_numero(item.get("amid"))
            item["ubicacion_actual"] = normalizar_texto(
                item.get("ubicacion_actual"),
                UBICACION_SIN_ASIGNAR,
            )
            item["nivel_alerta_global"] = normalizar_texto(item.get("nivel_alerta_global"), "OK")
            item["nivel_alerta_gps"] = normalizar_texto(item.get("nivel_alerta_gps"), "OK")
            item["nivel_alerta_bateria"] = normalizar_texto(item.get("nivel_alerta_bateria"), "OK")
            item["motivo_principal"] = normalizar_texto(item.get("motivo_principal"), "Sin alertas")
            item["accion_sugerida"] = normalizar_texto(item.get("accion_sugerida"), "")

            item["motivo_alerta_gps"] = normalizar_texto(item.get("motivo_alerta_gps"), "")
            item["motivo_alerta_bateria"] = normalizar_texto(item.get("motivo_alerta_bateria"), "")

            item["gps_cero_hoy"] = normalizar_numero(item.get("gps_cero_hoy"))
            item["gps_cero_hist"] = normalizar_numero(item.get("gps_cero_hist"))
            item["gps_cero_porc_hoy"] = normalizar_numero(item.get("gps_cero_porc_hoy"))
            item["gps_cero_porc_hist"] = normalizar_numero(item.get("gps_cero_porc_hist"))
            item["ultimo_gps_es_cero"] = normalizar_numero(item.get("ultimo_gps_es_cero"))
            item["racha_max_gps_cero"] = normalizar_numero(item.get("racha_max_gps_cero"))

            item["bateria_actual"] = item.get("bateria_actual")
            item["caidas_hoy"] = normalizar_numero(item.get("caidas_hoy"))
            item["caidas_hist"] = normalizar_numero(item.get("caidas_hist"))
            item["total_caidas"] = item["caidas_hist"]
            item["caidas_anteriores"] = max(
                item["caidas_hist"] - item["caidas_hoy"], 0
            )
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


def obtener_ubicaciones_alertas_disponibles():
    """Ubicaciones asignadas a los AMID activos que pueden excluirse."""

    ubicaciones_cache = cache.get(CACHE_KEY_UBICACIONES_ALERTAS)
    if ubicaciones_cache is not None:
        return ubicaciones_cache

    query = """
        SELECT ubicacion_actual
        FROM (
            SELECT DISTINCT
                NVL(TRIM(u.NOMBRE), :ubicacion_sin_asignar) AS ubicacion_actual
            FROM USR_LAB.VW_ALERTA_VALIDADOR_ACTIVA r
            LEFT JOIN USR_LAB.UBICACION_ESPERADA_VALIDADOR u
              ON u.AMID = r.AMID
        )
        ORDER BY ubicacion_actual
    """

    with obtener_conexion_oracle() as connection:
        cursor = connection.cursor()
        cursor.execute(query, {"ubicacion_sin_asignar": UBICACION_SIN_ASIGNAR})
        ubicaciones = [str(row[0]) for row in cursor.fetchall() if row and row[0]]

    cache.set(
        CACHE_KEY_UBICACIONES_ALERTAS,
        ubicaciones,
        CACHE_TIMEOUT_UBICACIONES_ALERTAS,
    )
    return ubicaciones


def buscar_amids_alertas(termino, limite=LIMITE_SUGERENCIAS_ALERTAS):
    """Busca AMID activos por prefijo sin cargar el catalogo completo."""

    termino = str(termino or "").strip()
    if len(termino) < MIN_CARACTERES_BUSQUEDA_ALERTAS or not termino.isdigit():
        return []

    limite = max(1, min(int(limite), MAX_LIMITE_SUGERENCIAS_ALERTAS))
    query = """
        SELECT amid
        FROM (
            SELECT r.AMID AS amid
            FROM USR_LAB.VW_ALERTA_VALIDADOR_ACTIVA r
            WHERE TO_CHAR(r.AMID) LIKE :patron
            ORDER BY r.AMID
        )
        WHERE ROWNUM <= :limite
    """

    with obtener_conexion_oracle() as connection:
        cursor = connection.cursor()
        cursor.execute(
            query,
            {
                "patron": f"{termino}%",
                "limite": limite,
            },
        )
        return [
            str(row[0])
            for row in cursor.fetchall()
            if row and row[0] is not None
        ]


def _normalizar_termino_busqueda(valor):
    texto = unicodedata.normalize("NFD", str(valor or "").casefold())
    return "".join(
        caracter for caracter in texto if not unicodedata.combining(caracter)
    )


def buscar_ubicaciones_alertas(termino, limite=LIMITE_SUGERENCIAS_ALERTAS):
    """Filtra el catalogo cacheado de ubicaciones sin enviarlo completo al HTML."""

    termino_normalizado = _normalizar_termino_busqueda(termino).strip()
    if len(termino_normalizado) < MIN_CARACTERES_BUSQUEDA_ALERTAS:
        return []

    limite = max(1, min(int(limite), MAX_LIMITE_SUGERENCIAS_ALERTAS))
    resultados = []

    for ubicacion in obtener_ubicaciones_alertas_disponibles():
        if termino_normalizado in _normalizar_termino_busqueda(ubicacion):
            resultados.append(ubicacion)
            if len(resultados) >= limite:
                break

    return resultados


def obtener_resumen_alertas(amids_excluidos=None, ubicaciones_excluidas=None):
    """
    Totales de AMID activos para las tarjetas superiores.

    Sin preferencias usa cache compartida. Un resumen personalizado se
    consulta directamente para no mezclar los datos de usuarios distintos.
    """

    usar_cache = not amids_excluidos and not ubicaciones_excluidas
    if usar_cache:
        resumen_cache = cache.get(CACHE_KEY_RESUMEN_ALERTAS)
        if resumen_cache is not None:
            return resumen_cache

    filtros, params = _armar_filtros_alertas(
        solo_con_alerta=False,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )
    where_sql = "WHERE " + " AND ".join(filtros) if filtros else ""

    query = f"""
        SELECT
            COUNT(*) AS total_validadores,
            SUM(CASE WHEN TIENE_ALERTA = 1 THEN 1 ELSE 0 END) AS total_alertas,
            SUM(CASE WHEN NIVEL_ALERTA_GLOBAL = 'CRITICA' THEN 1 ELSE 0 END) AS total_criticas,
            SUM(CASE WHEN NIVEL_ALERTA_GLOBAL = 'ALTA' THEN 1 ELSE 0 END) AS total_altas,
            SUM(CASE WHEN NIVEL_ALERTA_GLOBAL = 'ADVERTENCIA' THEN 1 ELSE 0 END) AS total_advertencias,
            SUM(CASE WHEN NIVEL_ALERTA_GLOBAL = 'OK' THEN 1 ELSE 0 END) AS total_ok,
            SUM(CASE WHEN NIVEL_ALERTA_GPS <> 'OK' THEN 1 ELSE 0 END) AS total_gps,
            SUM(CASE WHEN NIVEL_ALERTA_BATERIA <> 'OK' THEN 1 ELSE 0 END) AS total_bateria,
            SUM(NVL(CAIDAS_HIST, 0)) AS total_caidas_bateria,
            MAX(FECHA_ACTUALIZACION) AS ultima_actualizacion
        FROM USR_LAB.VW_ALERTA_VALIDADOR_ACTIVA r
        LEFT JOIN USR_LAB.UBICACION_ESPERADA_VALIDADOR u
          ON u.AMID = r.AMID
        {where_sql}
    """

    with obtener_conexion_oracle() as connection:
        cursor = connection.cursor()
        cursor.execute(query, params)
        row = cursor.fetchone()

    if not row:
        resumen = {
            "total_validadores": 0,
            "total_alertas": 0,
            "total_criticas": 0,
            "total_altas": 0,
            "total_advertencias": 0,
            "total_ok": 0,
            "total_gps": 0,
            "total_bateria": 0,
            "total_caidas_bateria": 0,
            "ultima_actualizacion": None,
        }
    else:
        resumen = {
            "total_validadores": normalizar_numero(row[0]),
            "total_alertas": normalizar_numero(row[1]),
            "total_criticas": normalizar_numero(row[2]),
            "total_altas": normalizar_numero(row[3]),
            "total_advertencias": normalizar_numero(row[4]),
            "total_ok": normalizar_numero(row[5]),
            "total_gps": normalizar_numero(row[6]),
            "total_bateria": normalizar_numero(row[7]),
            "total_caidas_bateria": normalizar_numero(row[8]),
            "ultima_actualizacion": row[9],
        }

    if usar_cache:
        cache.set(
            CACHE_KEY_RESUMEN_ALERTAS,
            resumen,
            CACHE_TIMEOUT_RESUMEN_ALERTAS,
        )
    return resumen

def construir_querystring_filtro(
    amid="",
    nivel="",
    tipo_alerta="",
    problema="",
    estatus="",
    mostrar_todos=False,
    nivel_override=None,
):
    params = {}

    if amid:
        params["amid"] = amid

    nivel_final = nivel_override if nivel_override is not None else nivel
    if nivel_final:
        params["nivel"] = nivel_final

    if tipo_alerta:
        params["tipo_alerta"] = tipo_alerta

    if problema:
        params["problema"] = problema

    if estatus:
        params["estatus"] = estatus

    if mostrar_todos or nivel_final == "OK":
        params["mostrar_todos"] = "1"

    return urlencode(params)


def obtener_contexto_alertas(request, preferencias=None):
    preferencias = preferencias or {}
    amids_excluidos = preferencias.get("amids_excluidos", [])
    ubicaciones_excluidas = preferencias.get("ubicaciones_excluidas", [])
    amid = request.GET.get("amid", "").strip()
    nivel = request.GET.get("nivel", "").strip().upper()
    tipo_alerta = request.GET.get("tipo_alerta", "").strip().upper()
    problema = request.GET.get("problema", "").strip()
    estatus = request.GET.get("estatus", "").strip().upper()
    mostrar_todos = request.GET.get("mostrar_todos") == "1"
    page = request.GET.get("page", "1").strip()

    try:
        page_num = int(page) if page else 1
    except ValueError:
        page_num = 1

    page_num = max(page_num, 1)

    solo_con_alerta = not mostrar_todos and nivel != "OK"

    total_alertas = contar_alertas_validadores(
        amid=amid if amid else None,
        nivel=nivel if nivel else None,
        tipo_alerta=tipo_alerta if tipo_alerta else None,
        problema=problema if problema else None,
        estatus=estatus if estatus else None,
        solo_con_alerta=solo_con_alerta,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )

    total_paginas = max(1, (total_alertas + ALERTAS_POR_PAGINA - 1) // ALERTAS_POR_PAGINA)

    if page_num > total_paginas:
        page_num = total_paginas

    offset = (page_num - 1) * ALERTAS_POR_PAGINA

    alertas = obtener_alertas_validadores(
        amid=amid if amid else None,
        nivel=nivel if nivel else None,
        tipo_alerta=tipo_alerta if tipo_alerta else None,
        problema=problema if problema else None,
        estatus=estatus if estatus else None,
        solo_con_alerta=solo_con_alerta,
        limite=ALERTAS_POR_PAGINA,
        offset=offset,
        ordenar=True,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )

    page_obj = {
        "numero": page_num,
        "total": total_paginas,
        "has_previous": page_num > 1,
        "has_next": page_num < total_paginas,
        "previous_page_number": page_num - 1 if page_num > 1 else None,
        "next_page_number": page_num + 1 if page_num < total_paginas else None,
        "start_index": offset + 1 if total_alertas else 0,
        "end_index": min(offset + len(alertas), total_alertas),
    }

    resumen = obtener_resumen_alertas(
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )

    querystring_sin_page = construir_querystring_filtro(
        amid=amid,
        nivel=nivel,
        tipo_alerta=tipo_alerta,
        problema=problema,
        estatus=estatus,
        mostrar_todos=mostrar_todos,
    )

    cards_filtros = {
        "critica": construir_querystring_filtro(
            amid=amid,
            nivel=nivel,
            tipo_alerta=tipo_alerta,
            problema=problema,
            estatus=estatus,
            mostrar_todos=mostrar_todos,
            nivel_override="CRITICA",
        ),
        "alta": construir_querystring_filtro(
            amid=amid,
            nivel=nivel,
            tipo_alerta=tipo_alerta,
            problema=problema,
            estatus=estatus,
            mostrar_todos=mostrar_todos,
            nivel_override="ALTA",
        ),
        "advertencia": construir_querystring_filtro(
            amid=amid,
            nivel=nivel,
            tipo_alerta=tipo_alerta,
            problema=problema,
            estatus=estatus,
            mostrar_todos=mostrar_todos,
            nivel_override="ADVERTENCIA",
        ),
        "ok": construir_querystring_filtro(
            amid=amid,
            nivel=nivel,
            tipo_alerta=tipo_alerta,
            problema=problema,
            estatus=estatus,
            mostrar_todos=True,
            nivel_override="OK",
        ),
    }

    return {
        "alertas": alertas,
        "resumen_alertas": resumen,
        "filtro_amid": amid,
        "filtro_nivel": nivel,
        "filtro_tipo_alerta": tipo_alerta,
        "filtro_problema": problema,
        "filtro_estatus": estatus,
        "mostrar_todos": mostrar_todos,
        "page_obj": page_obj,
        "querystring_sin_page": querystring_sin_page,
        "cards_filtros": cards_filtros,
        "alertas_por_pagina": ALERTAS_POR_PAGINA,
    }
