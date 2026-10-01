import logging

from django.conf import settings
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

# Antigüedad de los datos para el semáforo del sidebar. Son minutos y se
# duplican en el HTML como data-umbral-aviso / data-umbral-error para que el
# reloj de `sidebar.js` no repita la política: la lee del DOM.
UMBRAL_AVISO_MINUTOS = 60
UMBRAL_ERROR_MINUTOS = 180

# El entorno se muestra siempre salvo en producción: es la señal de que se
# está mirando un entorno que no es el real.
ETIQUETAS_AMBIENTE = {
    "DESARROLLO": "DESARROLLO",
    "PRE": "PREPRODUCCIÓN",
}


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


def _segundos_desde(momento, ahora):
    """
    Segundos transcurridos desde `momento` hasta `ahora`.

    Las fechas que llegan desde Oracle llegan sin zona horaria y ya están en
    hora local (ver `normalizar_fecha_para_comparar`), así que se les fija la
    zona de `TIME_ZONE` antes de restarlas. Un reloj adelantado en origen no
    debe producir texto negativo.
    """

    if momento is None:
        return None

    if not timezone.is_aware(momento):
        momento = timezone.make_aware(momento, timezone.get_current_timezone())

    return max(0, int((ahora - momento).total_seconds()))


def _texto_relativo(segundos):
    if segundos < 60:
        return "hace instantes"

    if segundos < 3600:
        return f"hace {segundos // 60} min"

    if segundos < 86400:
        return f"hace {segundos // 3600} h"

    return f"hace {segundos // 86400} días"


def estado_frescura(momento, ahora=None):
    """
    Traduce una fecha de Oracle a la tarjeta del sidebar: cuánto tiempo tiene
    y en qué estado está. Sin datos no es un error, es un estado propio, para
    no presentar un vacío como si fuera una caída.
    """

    ahora = ahora or timezone.now()
    segundos = _segundos_desde(momento, ahora)

    base = {
        "umbral_aviso": UMBRAL_AVISO_MINUTOS,
        "umbral_error": UMBRAL_ERROR_MINUTOS,
    }

    if segundos is None:
        return {
            **base,
            "estado": "sin-datos",
            "texto": "Sin datos",
            "minutos": None,
            "epoch": None,
        }

    minutos = segundos // 60

    if minutos >= UMBRAL_ERROR_MINUTOS:
        estado = "error"
    elif minutos >= UMBRAL_AVISO_MINUTOS:
        estado = "aviso"
    else:
        estado = "ok"

    if not timezone.is_aware(momento):
        momento = timezone.make_aware(momento, timezone.get_current_timezone())

    return {
        **base,
        "estado": estado,
        "texto": _texto_relativo(segundos),
        "minutos": minutos,
        "epoch": int(momento.timestamp()),
    }


def _iniciales_usuario(usuario):
    nombre = (usuario.get_full_name() or usuario.get_username() or "").strip()

    if not nombre:
        return "?"

    palabras = [palabra for palabra in nombre.split() if palabra]

    if len(palabras) == 1:
        return palabras[0][:2].upper()

    return (palabras[0][0] + palabras[-1][0]).upper()


def _etiqueta_rol(usuario):
    """
    Misma convención que usa la lista de usuarios del panel Perfil: Admin para
    superusuario, si no los grupos, si no "Sin rol".
    """

    if usuario.is_superuser:
        return "Admin"

    grupos = list(usuario.groups.values_list("name", flat=True))

    return ", ".join(grupos) if grupos else "Sin rol"


def metadatos_app(request):
    """
    Versión, entorno e identidad del usuario.

    Corre también para anónimos porque el login muestra versión y entorno. Lo
    único que exige sesión es la identidad, para no resolver un usuario que
    no existe.
    """

    contexto = {
        "VERSION_APP": settings.VERSION_APP,
        "AMBIENTE": settings.AMBIENTE,
        "ambiente_etiqueta": ETIQUETAS_AMBIENTE.get(settings.AMBIENTE, ""),
        "ambiente_es_preproduccion": settings.AMBIENTE in ETIQUETAS_AMBIENTE,
    }

    usuario = getattr(request, "user", None)

    if usuario is None or not usuario.is_authenticated:
        return contexto

    contexto.update(
        {
            "usuario_nombre": usuario.get_full_name() or usuario.get_username(),
            "usuario_rol": _etiqueta_rol(usuario),
            "usuario_iniciales": _iniciales_usuario(usuario),
        }
    )

    return contexto


def datos_actualizacion_dashboard(request):
    """
    Estado de los datos que consume el sidebar del dashboard.

    Si el usuario no está autenticado, no se consulta Oracle.
    Esto evita lentitud innecesaria en login/logout.
    """

    if not request.user.is_authenticated:
        return {}

    ultima_carga = obtener_ultima_carga_datos_oracle()
    ultima_version = obtener_ultima_version_zp_oracle()

    return {
        "ultima_carga_datos": ultima_carga,
        "ultima_actualizacion_version_zp": ultima_version,
        "estado_carga_datos": estado_frescura(ultima_carga),
        "estado_version_zp": estado_frescura(ultima_version),
    }

