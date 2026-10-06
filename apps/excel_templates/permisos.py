"""
Permisos del modulo de plantillas Excel.

Las plantillas son formato de negocio, no un archivo cualquiera: quien puede
exportar una plantilla vacia es quien esta autorizado a ver transacciones. Se
reusa el gate de `apps.transacciones.permisos` para no inventar una segunda
politica que se pueda desincronizar de la primera.

La captura es un caso aparte. Subir un Excel crea una version nueva y, por
defecto, deja esa version vigente: es la unica operacion del modulo que escribe
en la base, asi que no puede quedar abierta a quien solo tiene permiso de
**ver** transacciones. Por eso hay un segundo gate, `usuario_puede_capturar`,
que se apoya en `EXCEL_TEMPLATES_GRUPOS_CAPTURA` (por defecto `Admin`).

Dividirlo asi deja a una SONDA descargar la plantilla vigente, que es lo que le
corresponde, sin que pueda cambiar cual es la vigente.
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from apps.transacciones.permisos import (
    requiere_permiso_transacciones,
)

#: Alias local para que las vistas del modulo no importen de otra app.
requiere_permiso_plantillas = requiere_permiso_transacciones

MENSAJE_SIN_PERMISO = "No tienes permisos para ver esta sección."

MENSAJE_SIN_PERMISO_CAPTURA = (
    "No tienes permisos para subir plantillas. La captura queda para "
    "superusuarios y para el grupo configurado en "
    "EXCEL_TEMPLATES_GRUPOS_CAPTURA."
)


def usuario_puede_capturar(user):
    """Indica si el usuario puede crear versiones nuevas de una plantilla.

    El superusuario siempre pasa, igual que en el resto del dashboard. La lista
    de grupos sale de configuracion; vacia deja la captura solo para
    superusuarios, que es el fallo seguro: por defecto no se puede escribir.
    """

    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    grupos = settings.EXCEL_TEMPLATES_GRUPOS_CAPTURA
    if not grupos:
        return False

    return user.groups.filter(name__in=grupos).exists()


def requiere_permiso_captura(vista):
    """
    Exige sesion, acceso a Transacciones **y** permiso de captura.

    Son dos gates y no uno porque responden a preguntas distintas: el primero
    es "puede ver el monitor", el segundo "puede escribir en la base de
    plantillas". Encadenarlos deja el 403 con un mensaje que dice cual de los
    dos fallo, que con un unico mensaje seria adivinar.
    """

    @wraps(vista)
    @login_required
    def _envuelta(request, *args, **kwargs):
        from apps.transacciones.permisos import usuario_puede_ver_transacciones

        if not usuario_puede_ver_transacciones(request.user):
            return HttpResponseForbidden(MENSAJE_SIN_PERMISO)

        if not usuario_puede_capturar(request.user):
            return HttpResponseForbidden(MENSAJE_SIN_PERMISO_CAPTURA)

        return vista(request, *args, **kwargs)

    return _envuelta