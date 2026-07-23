from apps.dashboard.services.oracle_connection import obtener_conexion_oracle

ORDEN_PRIORIDAD = {
    "CRITICA": 1,
    "ALTA": 2,
    "ADVERTENCIA": 3,
    "OK": 4,
}


def normalizar_numero(valor, default=0):
    if valor is None:
        return default
    return valor


def normalizar_texto(valor, default=""):
    if valor is None:
        return default
    return str(valor)


def obtener_alertas_validadores(
    amid=None,
    nivel=None,
    tipo_alerta=None,
    solo_con_alerta=True,
    limite=500,
):
    """
    Lee alertas desde USR_LAB.ALERTA_VALIDADOR_RESUMEN.
    No calcula reglas. Solo consulta la tabla resumen ya calculada por Oracle.
    """

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

    where_sql = ""
    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    query = f"""
        SELECT *
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
            ORDER BY
                CASE NIVEL_ALERTA_GLOBAL
                    WHEN 'CRITICA' THEN 1
                    WHEN 'ALTA' THEN 2
                    WHEN 'ADVERTENCIA' THEN 3
                    ELSE 4
                END,
                AMID
        )
        WHERE ROWNUM <= :limite
    """

    params["limite"] = int(limite)

    alertas = []

    with obtener_conexion_oracle() as connection:
        cursor = connection.cursor()
        cursor.execute(query, params)

        columnas = [col[0].lower() for col in cursor.description]

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
    mostrar_todos = request.GET.get("mostrar_todos") == "1"

    alertas = obtener_alertas_validadores(
        amid=amid if amid else None,
        nivel=nivel if nivel else None,
        tipo_alerta=tipo_alerta if tipo_alerta else None,
        solo_con_alerta=not mostrar_todos,
        limite=1000,
    )

    resumen = obtener_resumen_alertas()

    return {
        "alertas": alertas,
        "resumen_alertas": resumen,
        "filtro_amid": amid,
        "filtro_nivel": nivel,
        "filtro_tipo_alerta": tipo_alerta,
        "mostrar_todos": mostrar_todos,
    }