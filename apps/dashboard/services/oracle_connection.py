import oracledb
from django.conf import settings


def obtener_conexion_oracle():
    """
    Crea y retorna una conexión a Oracle usando los datos definidos en settings.py.
    """

    dsn = oracledb.makedsn(
        settings.ORACLE_HOST,
        settings.ORACLE_PORT,
        sid=settings.ORACLE_SID,
    )

    conexion = oracledb.connect(
        user=settings.ORACLE_USER,
        password=settings.ORACLE_PASSWORD,
        dsn=dsn,
    )

    return conexion