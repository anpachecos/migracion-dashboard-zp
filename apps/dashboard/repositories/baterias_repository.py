from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


def obtener_ultimo_registro(amid):
    query = """
        SELECT *
        FROM (
            SELECT
                ID,
                AMID,
                FEC_DESCARGA,
                FEC_ESTADO,
                BUSID,
                OP,
                VERSION,
                PATENTE,
                TD01,
                TD04,
                FECHA_HORA,
                PORCENTAJE_BATERIA,
                IS_CONTIENE_BATERIA,
                IS_ERROR_OBTENER_BATERIA
            FROM USR_LAB.VW_ESTATUS_ZP_DJANGO
            WHERE AMID = :amid
            ORDER BY FECHA_HORA DESC
        )
        WHERE ROWNUM = 1
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, {"amid": int(amid)})
            fila = cursor.fetchone()

            if not fila:
                return None

            columnas = [col[0].lower() for col in cursor.description]
            return dict(zip(columnas, fila))


def obtener_bloques_bateria(amid, fecha_inicio, fecha_fin):
    query = """
        SELECT
            AMID,
            FECHA_HORA_BLOQUE,
            FECHA_BLOQUE,
            HORA_BLOQUE,
            PORCENTAJE_BATERIA,
            FECHA_HORA_ORIGINAL,
            ID_ORACLE,
            DIFERENCIA_MINUTOS,
            TIENE_DATO
        FROM USR_LAB.BATERIA_BLOQUE_30MIN
        WHERE AMID = :amid
          AND FECHA_HORA_BLOQUE >= :fecha_inicio
          AND FECHA_HORA_BLOQUE < :fecha_fin
        ORDER BY FECHA_HORA_BLOQUE
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "amid": int(amid),
                    "fecha_inicio": fecha_inicio,
                    "fecha_fin": fecha_fin,
                },
            )

            columnas = [col[0].lower() for col in cursor.description]
            return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def obtener_detalle_caidas_bateria(amid):
    query = """
        SELECT
            AMID,
            FECHA_CAIDA_DESDE,
            FECHA_CAIDA,
            BATERIA_DESDE,
            BATERIA_HASTA,
            CAIDA_DIF,
            FECHA_CALCULO
        FROM USR_LAB.ALERTA_BATERIA_CAIDA_EVENTO
        WHERE AMID = :amid
        ORDER BY FECHA_CAIDA DESC
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, {"amid": int(amid)})
            columnas = [col[0].lower() for col in cursor.description]
            return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def obtener_resumen_alerta_bateria(amid):
    query = """
        SELECT
            AMID,
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
            BATERIA_ACTUAL,
            ULTIMA_FECHA_BATERIA,
            NIVEL_ALERTA_BATERIA,
            MOTIVO_ALERTA_BATERIA,
            FECHA_ACTUALIZACION
        FROM USR_LAB.ALERTA_VALIDADOR_RESUMEN
        WHERE AMID = :amid
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, {"amid": int(amid)})
            fila = cursor.fetchone()

            if not fila:
                return None

            columnas = [col[0].lower() for col in cursor.description]
            return dict(zip(columnas, fila))
