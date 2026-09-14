from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


def obtener_resumenes_estado():
    query_bateria = """
            SELECT
                COUNT(*) AS TOTAL_BLOQUES,
                SUM(
                    CASE
                        WHEN TIENE_DATO = 1 THEN 1
                        ELSE 0
                    END
                ) AS BLOQUES_CON_DATO,
                MAX(FECHA_HORA_BLOQUE) AS ULTIMO_BLOQUE,
                MAX(
                    CASE
                        WHEN TIENE_DATO = 1 THEN FECHA_HORA_BLOQUE
                    END
                ) AS ULTIMO_BLOQUE_CON_DATO,
                MAX(FECHA_ACTUALIZACION) AS ULTIMA_ACTUALIZACION
            FROM USR_LAB.BATERIA_BLOQUE_30MIN
        """
    query_ubicaciones = """
            SELECT
                COUNT(*) AS TOTAL_UBICACIONES,
                MAX(FECHA_CARGA) AS ULTIMA_CARGA
            FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
        """
    query_historial = """
            SELECT
                COUNT(*) AS HISTORIALES_VIGENTES
            FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA
            WHERE FECHA_FIN_VIGENCIA IS NULL
        """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query_bateria)
            fila_bateria = cursor.fetchone()

            cursor.execute(query_ubicaciones)
            fila_ubicaciones = cursor.fetchone()

            cursor.execute(query_historial)
            fila_historial = cursor.fetchone()

    return fila_bateria, fila_ubicaciones, fila_historial


def obtener_sysdate():
    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT SYSDATE FROM dual")
            return cursor.fetchone()
