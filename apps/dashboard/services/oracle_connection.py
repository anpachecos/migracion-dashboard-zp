import oracledb
from django.conf import settings


_oracle_client_inicializado = False


def inicializar_oracle_client():
    """
    Inicializa Oracle Client en modo thick.
    Necesario para conectarse a servidores Oracle antiguos.
    """
    global _oracle_client_inicializado

    if _oracle_client_inicializado:
        return

    if settings.ORACLE_CLIENT_PATH:
        oracledb.init_oracle_client(lib_dir=settings.ORACLE_CLIENT_PATH)
    else:
        oracledb.init_oracle_client()

    _oracle_client_inicializado = True


def obtener_conexion_oracle():
    """
    Crea y retorna una conexión a Oracle usando los datos definidos en settings.py.
    """

    inicializar_oracle_client()

    dsn = oracledb.makedsn(
        settings.ORACLE_HOST,
        settings.ORACLE_PORT,
        service_name=settings.ORACLE_SERVICE_NAME,
    )

    conexion = oracledb.connect(
        user=settings.ORACLE_USER,
        password=settings.ORACLE_PASSWORD,
        dsn=dsn,
    )

    return conexion