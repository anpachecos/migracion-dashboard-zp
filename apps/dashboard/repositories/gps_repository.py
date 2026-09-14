from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


def obtener_registros_gps(amid, fecha_inicio, fecha_fin):
    query_anterior = """
        SELECT FECHA_HORA
        FROM (
            SELECT FECHA_HORA
            FROM USR_LAB.VW_ESTATUS_ZP_DJANGO
            WHERE AMID = :amid
              AND FECHA_REGISTRO < TO_DATE(:fecha_inicio, 'YYYY-MM-DD HH24:MI:SS')
            ORDER BY FECHA_REGISTRO DESC, ID DESC
        )
        WHERE ROWNUM = 1
    """

    query = """
        SELECT
            ID,
            AMID,
            FEC_DESCARGA,
            FEC_ESTADO,
            FECHA_HORA,
            FECHA_REGISTRO,
            LATITUD,
            LONGITUD,
            PORCENTAJE_BATERIA,
            IS_CONTIENE_GPS,
            IS_ERROR_OBTENER_GPS
        FROM USR_LAB.VW_ESTATUS_ZP_DJANGO
        WHERE AMID = :amid
          AND FECHA_REGISTRO >= TO_DATE(:fecha_inicio, 'YYYY-MM-DD HH24:MI:SS')
          AND FECHA_REGISTRO < TO_DATE(:fecha_fin, 'YYYY-MM-DD HH24:MI:SS')
        ORDER BY FECHA_REGISTRO, ID
    """

    parametros = {
        "amid": int(amid),
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
    }

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                query_anterior,
                {
                    "amid": parametros["amid"],
                    "fecha_inicio": parametros["fecha_inicio"],
                },
            )
            fila_anterior = cursor.fetchone()

            cursor.execute(query, parametros)
            columnas = [col[0].lower() for col in cursor.description]
            registros = [
                dict(zip(columnas, fila))
                for fila in cursor.fetchall()
            ]

    return {
        "fecha_hora_anterior": fila_anterior[0] if fila_anterior else None,
        "registros": registros,
    }


def obtener_ultimo_registro_gps_valido(amid):
    query = """
        SELECT *
        FROM (
            SELECT
                ID,
                AMID,
                FEC_DESCARGA,
                FEC_ESTADO,
                FECHA_HORA,
                LATITUD,
                LONGITUD,
                PORCENTAJE_BATERIA,
                IS_CONTIENE_GPS,
                IS_ERROR_OBTENER_GPS
            FROM USR_LAB.VW_ESTATUS_ZP_DJANGO
            WHERE AMID = :amid
              AND FECHA_HORA IS NOT NULL
              AND LATITUD IS NOT NULL
              AND LONGITUD IS NOT NULL
              AND NOT (LATITUD = 0 AND LONGITUD = 0)
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


def obtener_datos_ubicacion_amid(amid):
    query_historial = """
        SELECT
            AMID,
            NOMBRE,
            LATITUD_ESPERADA,
            LONGITUD_ESPERADA,
            RADIO_METROS,
            OPERATIVA,
            ORIGEN_UBICACION,
            VERSION_ZP,
            ARCHIVO_ORIGEN,
            FECHA_INICIO_VIGENCIA,
            FECHA_FIN_VIGENCIA
        FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA
        WHERE AMID = :amid
        ORDER BY FECHA_INICIO_VIGENCIA
    """

    query_vigente = """
        SELECT
            AMID,
            NOMBRE,
            LATITUD_ESPERADA,
            LONGITUD_ESPERADA,
            RADIO_METROS,
            OPERATIVA,
            VERSION_ZP,
            ARCHIVO_ORIGEN,
            HORARIO,
            HORARIO_LABORAL_PM,
            HORARIO_SABADO,
            HORARIO_DOMINGO,
            FECHA_CARGA
        FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
        WHERE AMID = :amid
    """

    parametros = {"amid": str(amid).strip()}

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query_historial, parametros)
            columnas_historial = [col[0] for col in cursor.description]
            historial = [
                dict(zip(columnas_historial, fila))
                for fila in cursor.fetchall()
            ]

            cursor.execute(query_vigente, parametros)
            fila_vigente = cursor.fetchone()

            if fila_vigente:
                columnas_vigente = [col[0] for col in cursor.description]
                vigente = dict(zip(columnas_vigente, fila_vigente))
            else:
                vigente = None

    return {
        "historial": historial,
        "vigente": vigente,
    }
