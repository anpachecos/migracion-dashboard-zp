from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


SQL_ORDEN_ALERTAS = {
    "prioridad": """
        CASE NIVEL_ALERTA_GLOBAL
            WHEN 'CRITICA' THEN 1
            WHEN 'ALTA' THEN 2
            WHEN 'ADVERTENCIA' THEN 3
            WHEN 'OK' THEN 4
            ELSE 5
        END
    """.strip(),
    "gps": """
        CASE NIVEL_ALERTA_GPS
            WHEN 'CRITICA' THEN 1
            WHEN 'ALTA' THEN 2
            WHEN 'ADVERTENCIA' THEN 3
            WHEN 'OK' THEN 4
            ELSE 5
        END
    """.strip(),
    "bateria": """
        CASE NIVEL_ALERTA_BATERIA
            WHEN 'CRITICA' THEN 1
            WHEN 'ALTA' THEN 2
            WHEN 'ADVERTENCIA' THEN 3
            WHEN 'OK' THEN 4
            ELSE 5
        END
    """.strip(),
    "estatus": """
        CASE
            WHEN ULTIMO_ESTATUS >= TRUNC(SYSDATE)
             AND ULTIMO_ESTATUS >= SYSDATE - (1/24) THEN 1
            WHEN ULTIMO_ESTATUS >= TRUNC(SYSDATE) THEN 2
            ELSE 3
        END
    """.strip(),
}


def construir_orden_alertas(orden):
    segmentos = []
    for campo, direccion in orden:
        direccion_sql = "ASC" if direccion == "asc" else "DESC"
        segmentos.append(f"{SQL_ORDEN_ALERTAS[campo]} {direccion_sql}")

        if campo == "estatus":
            detalle_estatus = (
                "ULTIMO_ESTATUS DESC NULLS LAST"
                if direccion == "asc"
                else "ULTIMO_ESTATUS ASC NULLS FIRST"
            )
            segmentos.append(detalle_estatus)

    segmentos.append("AMID ASC")
    return "ORDER BY\n                " + ",\n                ".join(segmentos)


def construir_condicion_problema(problema):
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
    if not estatus:
        return None

    estatus = estatus.upper()
    mapping = {
        "CON_ESTATUS": "ULTIMO_ESTATUS >= TRUNC(SYSDATE) AND ULTIMO_ESTATUS >= SYSDATE - (1/24)",
        "ANTIGUO": "ULTIMO_ESTATUS >= TRUNC(SYSDATE) AND ULTIMO_ESTATUS < SYSDATE - (1/24)",
        "SIN_ESTATUS": "ULTIMO_ESTATUS IS NULL OR ULTIMO_ESTATUS < TRUNC(SYSDATE)",
    }
    return mapping.get(estatus)


def armar_filtros_alertas(
    amid=None,
    ubicacion=None,
    nivel=None,
    nivel_gps=None,
    nivel_bateria=None,
    tipo_alerta=None,
    problema=None,
    estatus=None,
    solo_con_alerta=True,
    amids_excluidos=None,
    ubicaciones_excluidas=None,
    ubicacion_sin_asignar="",
):
    filtros = []
    params = {}

    if solo_con_alerta:
        filtros.append("TIENE_ALERTA = 1")

    if amid:
        filtros.append("r.AMID = :amid")
        params["amid"] = int(amid)

    if ubicacion:
        params["ubicacion_sin_asignar"] = ubicacion_sin_asignar
        params["ubicacion"] = f"%{str(ubicacion).strip().upper()}%"
        filtros.append(
            "UPPER(NVL(TRIM(u.NOMBRE), :ubicacion_sin_asignar)) "
            "LIKE :ubicacion"
        )

    if nivel:
        filtros.append("NIVEL_ALERTA_GLOBAL = :nivel")
        params["nivel"] = nivel.upper()

    if nivel_gps:
        filtros.append("NIVEL_ALERTA_GPS = :nivel_gps")
        params["nivel_gps"] = nivel_gps.upper()

    if nivel_bateria:
        filtros.append("NIVEL_ALERTA_BATERIA = :nivel_bateria")
        params["nivel_bateria"] = nivel_bateria.upper()

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
        params["ubicacion_sin_asignar"] = ubicacion_sin_asignar
        filtros.append(
            "NVL(TRIM(u.NOMBRE), :ubicacion_sin_asignar) "
            f"NOT IN ({', '.join(binds_ubicaciones)})"
        )

    return filtros, params


def contar_alertas_validadores(ubicacion_sin_asignar, **filtros_semanticos):
    filtros, params = armar_filtros_alertas(
        ubicacion_sin_asignar=ubicacion_sin_asignar,
        **filtros_semanticos,
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

    return row[0] if row else None


def obtener_alertas_validadores(
    ubicacion_sin_asignar,
    limite,
    offset,
    ordenar,
    orden,
    **filtros_semanticos,
):
    filtros, params = armar_filtros_alertas(
        ubicacion_sin_asignar=ubicacion_sin_asignar,
        **filtros_semanticos,
    )
    where_sql = ""
    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    order_sql = ""
    if ordenar:
        order_sql = construir_orden_alertas(orden)
    else:
        order_sql = "ORDER BY AMID ASC"

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
    params["ubicacion_sin_asignar"] = ubicacion_sin_asignar

    with obtener_conexion_oracle() as connection:
        cursor = connection.cursor()
        cursor.execute(query, params)
        columnas = [col[0].lower() for col in cursor.description if col and col[0]]
        return [dict(zip(columnas, row)) for row in cursor.fetchall()]


def obtener_ubicaciones_alertas_disponibles(ubicacion_sin_asignar):
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
        cursor.execute(query, {"ubicacion_sin_asignar": ubicacion_sin_asignar})
        return [row[0] for row in cursor.fetchall() if row and row[0]]


def buscar_amids_alertas(termino, limite):
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
        return [row[0] for row in cursor.fetchall() if row and row[0] is not None]


def obtener_resumen_alertas(
    ubicacion_sin_asignar,
    amids_excluidos=None,
    ubicaciones_excluidas=None,
):
    filtros, params = armar_filtros_alertas(
        solo_con_alerta=False,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
        ubicacion_sin_asignar=ubicacion_sin_asignar,
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
        return cursor.fetchone()
