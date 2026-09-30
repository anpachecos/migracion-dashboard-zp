import logging

from django.core.cache import cache
from django.utils import timezone

from apps.dashboard.repositories import estado_dashboard_repository
from apps.dashboard.services.claves_cache import (
    CACHE_KEY_ULTIMA_CARGA_DATOS,
    CACHE_KEY_ULTIMA_VERSION_ZP,
)
from apps.dashboard.services.normalizacion import normalizar_fecha_para_comparar


logger = logging.getLogger(__name__)

CACHE_MISS = object()

# 5 minutos
CACHE_TIMEOUT_SEGUNDOS = 300


def obtener_ultima_carga_datos_oracle():
    """
    Obtiene el último bloque horario con datos desde Oracle.

    Se cachea por 5 minutos para evitar abrir conexión Oracle en cada cambio
    de página.
    """

    valor_cache = cache.get(CACHE_KEY_ULTIMA_CARGA_DATOS, CACHE_MISS)

    if valor_cache is not CACHE_MISS:
        return valor_cache

    ultima_carga = None

    try:
        resultado = estado_dashboard_repository.obtener_ultima_carga_datos()

        if resultado and resultado[0]:
            ultima_carga = normalizar_fecha_para_comparar(resultado[0])

    except Exception as error:
        logger.exception(
            "Error obteniendo última carga de datos Oracle para sidebar: %s",
            error,
        )
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

    Se cachea por 5 minutos para evitar abrir conexión Oracle en cada cambio
    de página.
    """

    valor_cache = cache.get(CACHE_KEY_ULTIMA_VERSION_ZP, CACHE_MISS)

    if valor_cache is not CACHE_MISS:
        return valor_cache

    ultima_version = None

    try:
        resultado = estado_dashboard_repository.obtener_ultima_version_zp()

        if resultado and resultado[0]:
            ultima_version = normalizar_fecha_para_comparar(resultado[0])

    except Exception as error:
        logger.exception(
            "Error obteniendo última versión ZP Oracle para sidebar: %s",
            error,
        )
        ultima_version = None

    cache.set(
        CACHE_KEY_ULTIMA_VERSION_ZP,
        ultima_version,
        CACHE_TIMEOUT_SEGUNDOS,
    )

    return ultima_version


def datos_actualizacion_dashboard(request):
    """
    Variables globales disponibles en el sidebar del dashboard.

    Si el usuario no está autenticado, no se consulta Oracle.
    Esto evita lentitud innecesaria en login/logout.
    """

    if not request.user.is_authenticated:
        return {}

    ultima_actualizacion = timezone.localtime(timezone.now())

    return {
        "ultima_actualizacion_dashboard": ultima_actualizacion,
        "ultima_carga_datos": obtener_ultima_carga_datos_oracle(),
        "ultima_actualizacion_version_zp": obtener_ultima_version_zp_oracle(),
    }
