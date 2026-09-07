from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


def sincronizar_amids_ubicaciones_oracle():
    """
    Ejecuta la sincronización definida en Oracle y comprueba su resultado.

    Django no decide ubicaciones ni escribe las tablas: solamente invoca el
    mismo procedimiento utilizado por el job programado.
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            ubicaciones_creadas_var = cursor.var(int)
            historiales_creados_var = cursor.var(int)

            cursor.callproc(
                "USR_LAB.PRC_SINC_UBIC_AMID",
                [ubicaciones_creadas_var, historiales_creados_var],
            )

            cursor.execute(
                """
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM USR_LAB.AMID_MAESTRO_ALERTAS m
                        WHERE m.ACTIVO = 1
                          AND NOT EXISTS (
                              SELECT 1
                              FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR u
                              WHERE TRIM(u.AMID) =
                                    TRIM(CAST(m.AMID AS VARCHAR2(20)))
                          )
                    ) AS sin_ubicacion,
                    (
                        SELECT COUNT(*)
                        FROM USR_LAB.AMID_MAESTRO_ALERTAS m
                        JOIN USR_LAB.UBICACION_ESPERADA_VALIDADOR u
                          ON TRIM(u.AMID) =
                             TRIM(CAST(m.AMID AS VARCHAR2(20)))
                        WHERE m.ACTIVO = 1
                          AND NOT EXISTS (
                              SELECT 1
                              FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA h
                              WHERE TRIM(h.AMID) = TRIM(u.AMID)
                                AND h.FECHA_FIN_VIGENCIA IS NULL
                          )
                    ) AS sin_historial_abierto
                FROM dual
                """
            )
            fila_validacion = cursor.fetchone() or (0, 0)
            ubicaciones_creadas = int(ubicaciones_creadas_var.getvalue() or 0)
            historiales_creados = int(historiales_creados_var.getvalue() or 0)

    return {
        "ubicaciones_creadas": ubicaciones_creadas,
        "historiales_creados": historiales_creados,
        "sin_ubicacion": int(fila_validacion[0] or 0),
        "sin_historial_abierto": int(fila_validacion[1] or 0),
    }
