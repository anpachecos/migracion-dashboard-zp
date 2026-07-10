import threading

from django.core.cache import cache
from django.utils import timezone

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


CACHE_KEY_ULTIMA_CARGA_DATOS = "dashboard_ultima_carga_datos_oracle"
CACHE_KEY_ULTIMA_VERSION_ZP = "dashboard_ultima_version_zp_oracle"
CACHE_MISS = object()

CACHE_TIMEOUT_SEGUNDOS = 300

_warmup_thread_running = False
_warmup_thread_lock = threading.Lock()


def normalizar_fecha_oracle(fecha):
    """
    Convierte una fecha Oracle a datetime compatible con templates Django.

    No usamos timezone.localtime() para datos Oracle porque las fechas ya vienen
    con la hora correcta desde la base.
    """

    if not fecha:
        return None

    if timezone.is_aware(fecha):
        return timezone.make_naive(fecha)

    return fecha


def obtener_ultima_carga_datos_oracle():
    """
    Obtiene el último bloque horario con datos desde Oracle.

    Se cachea por 60 segundos para evitar abrir conexión Oracle en cada cambio
    de página.
    """

    valor_cache = cache.get(CACHE_KEY_ULTIMA_CARGA_DATOS, CACHE_MISS)

    if valor_cache is not CACHE_MISS:
        return valor_cache

    query = """
        SELECT MAX(FECHA_HORA_BLOQUE)
        FROM USR_LAB.BATERIA_BLOQUE_30MIN
        WHERE TIENE_DATO = 1
    """

    ultima_carga = None

    try:
        with obtener_conexion_oracle() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(query)
                resultado = cursor.fetchone()

        if resultado and resultado[0]:
            ultima_carga = normalizar_fecha_oracle(resultado[0])

    except Exception:
        ultima_carga = None

    cache.set(
        CACHE_KEY_ULTIMA_CARGA_DATOS,
        ultima_carga,
        CACHE_TIMEOUT_SEGUNDOS,
    )

    return ultima_carga


def obtener_ultima_version_zp_oracle():
    """
    Obtiene la última fecha de carga de la versión ZP desde Oracle.
    """

    valor_cache = cache.get(CACHE_KEY_ULTIMA_VERSION_ZP, CACHE_MISS)

    if valor_cache is not CACHE_MISS:
        return valor_cache

    query = """
        SELECT MAX(FECHA_CARGA)
        FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
    """

    ultima_version = None

    try:
        with obtener_conexion_oracle() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(query)
                resultado = cursor.fetchone()

        if resultado and resultado[0]:
            ultima_version = normalizar_fecha_oracle(resultado[0])

    except Exception:
        ultima_version = None

    cache.set(
        CACHE_KEY_ULTIMA_VERSION_ZP,
        ultima_version,
        CACHE_TIMEOUT_SEGUNDOS,
    )

    return ultima_version


def _iniciar_precarga_datos_actualizacion():
    """
    Precalienta los valores de Oracle en segundo plano para que el dashboard
    no espere a la conexión en la petición inicial.
    """

    global _warmup_thread_running

    if _warmup_thread_running:
        return

    with _warmup_thread_lock:
        if _warmup_thread_running:
            return
        _warmup_thread_running = True

    def _ejecutar_precarga():
        try:
            obtener_ultima_carga_datos_oracle()
            obtener_ultima_version_zp_oracle()
        finally:
            global _warmup_thread_running
            with _warmup_thread_lock:
                _warmup_thread_running = False

    threading.Thread(target=_ejecutar_precarga, daemon=True).start()


def datos_actualizacion_dashboard(request):
    """
    Variables globales disponibles en el sidebar del dashboard.

    Importante:
    Si el usuario no está autenticado, no consultamos Oracle.
    Esto evita lentitud innecesaria en login/logout.
    """

    if not request.user.is_authenticated:
        return {}

    ultima_actualizacion = timezone.localtime(timezone.now())

    datos_carga = cache.get(CACHE_KEY_ULTIMA_CARGA_DATOS, CACHE_MISS)
    datos_version = cache.get(CACHE_KEY_ULTIMA_VERSION_ZP, CACHE_MISS)

    if datos_carga is CACHE_MISS or datos_version is CACHE_MISS:
        _iniciar_precarga_datos_actualizacion()

    return {
        "ultima_actualizacion_dashboard": ultima_actualizacion,
        "ultima_carga_datos": datos_carga if datos_carga is not CACHE_MISS else None,
        "ultima_actualizacion_version_zp": datos_version if datos_version is not CACHE_MISS else None,
    }