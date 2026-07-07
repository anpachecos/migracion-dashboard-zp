import oracledb
from django.conf import settings


_oracle_client_inicializado = False
_pool_oracle = None


def inicializar_oracle_client():
    """
    Inicializa Oracle Client en modo thick.
    Necesario para conectarse a servidores Oracle antiguos.
    """

    global _oracle_client_inicializado

    if _oracle_client_inicializado:
        return

    try:
        if settings.ORACLE_CLIENT_PATH:
            oracledb.init_oracle_client(lib_dir=settings.ORACLE_CLIENT_PATH)
        else:
            oracledb.init_oracle_client()
    except oracledb.ProgrammingError:
        # Puede ocurrir si el cliente ya fue inicializado por el autoreload
        # o por otro módulo en el mismo proceso.
        pass

    _oracle_client_inicializado = True


def obtener_dsn_oracle():
    return oracledb.makedsn(
        settings.ORACLE_HOST,
        settings.ORACLE_PORT,
        service_name=settings.ORACLE_SERVICE_NAME,
    )


def obtener_pool_oracle():
    """
    Crea un pool de conexiones reutilizable.
    Evita abrir una conexión Oracle desde cero en cada consulta.
    """

    global _pool_oracle

    inicializar_oracle_client()

    if _pool_oracle is None:
        _pool_oracle = oracledb.create_pool(
            user=settings.ORACLE_USER,
            password=settings.ORACLE_PASSWORD,
            dsn=obtener_dsn_oracle(),
            min=1,
            max=4,
            increment=1,
            getmode=oracledb.POOL_GETMODE_WAIT,
        )

    return _pool_oracle


def obtener_conexion_oracle():
    """
    Retorna una conexión Oracle desde el pool.
    Se puede usar con:

        with obtener_conexion_oracle() as conexion:
            ...
    """

    pool = obtener_pool_oracle()
    return pool.acquire()