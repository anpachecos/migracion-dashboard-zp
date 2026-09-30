from apps.dashboard.services import oracle_connection
from apps.dashboard.services import oracle_cursor


def obtener_datos_horario_zp(amid):
    query = """
        SELECT AMID, NOMBRE, HORARIO, HORARIO_LABORAL_PM,
               HORARIO_SABADO, HORARIO_DOMINGO
        FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
        WHERE AMID = :amid
    """

    with oracle_connection.obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, {"amid": str(amid).strip()})
            return oracle_cursor.mapear_fila(cursor, minusculas=False)
