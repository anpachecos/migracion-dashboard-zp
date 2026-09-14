from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


def obtener_datos_horario_zp(amid):
    query = """
        SELECT AMID, NOMBRE, HORARIO, HORARIO_LABORAL_PM,
               HORARIO_SABADO, HORARIO_DOMINGO
        FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
        WHERE AMID = :amid
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, {"amid": str(amid).strip()})
            fila = cursor.fetchone()

            if not fila:
                return None

            columnas = [col[0] for col in cursor.description]
            return dict(zip(columnas, fila))
