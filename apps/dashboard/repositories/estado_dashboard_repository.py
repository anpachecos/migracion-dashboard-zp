from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


def obtener_ultima_carga_datos():
    query = """
        SELECT MAX(FECHA_HORA_BLOQUE)
        FROM USR_LAB.BATERIA_BLOQUE_30MIN
        WHERE TIENE_DATO = 1
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchone()


def obtener_ultima_version_zp():
    query = """
        SELECT MAX(FECHA_CARGA)
        FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchone()


def obtener_registros_completos(amid, fecha_inicio, fecha_fin):
    query = """
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
            TABLA,
            VER_TABLA,
            FECHA_HORA,
            IS_CONTIENE_BATERIA,
            IS_CONTIENE_GPS,
            IS_CONTIENE_TIEMPO_VIDA,
            IS_ERROR_OBTENER_BATERIA,
            IS_ERROR_OBTENER_GPS,
            IS_ERROR_OBTENER_TIEMPO_VIDA,
            LATITUD,
            LONGITUD,
            PORCENTAJE_BATERIA,
            TIEMPO_VIDA,
            FECHA_REGISTRO
        FROM USR_LAB.VW_ESTATUS_ZP_DJANGO
        WHERE AMID = :amid
          AND FECHA_HORA >= TO_DATE(:fecha_inicio, 'YYYY-MM-DD HH24:MI:SS')
          AND FECHA_HORA < TO_DATE(:fecha_fin, 'YYYY-MM-DD HH24:MI:SS')
        ORDER BY FECHA_HORA
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
            return [
                dict(zip(columnas, fila))
                for fila in cursor.fetchall()
            ]
