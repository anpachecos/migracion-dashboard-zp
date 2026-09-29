"""
Autorización del módulo de Transacciones.

La sección es de solo lectura, pero no es pública: únicamente la ven los
superusuarios y los miembros de los grupos configurados en
`TRX_GRUPOS_PERMITIDOS` (por defecto `Admin` y `SONDA`).

La política de qué grupos acceden vive en configuración y no aquí, para no
requerir un despliegue al cambiar quién entra. Los nombres son case-sensitive
y deben coincidir con los de `auth_group`: `SONDA` no es `Sonda`. La
pertenencia al grupo sí se resuelve siempre contra la base de datos.

Se replica a propósito la semántica de `usuario_es_admin` en
`apps/dashboard/views.py`, que ya considera admin tanto al superusuario como
al grupo `Admin`. El gate de alertas no se toca: vive en otro módulo y está
en staging por BKL-002C. `TRX_GRUPOS_PERMITIDOS` no altera ese gate.
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

MENSAJE_SIN_PERMISO = "No tienes permisos para ver esta sección."


def usuario_puede_ver_transacciones(user):
    """Indica si el usuario tiene acceso a la sección de Transacciones.

    Una sola consulta para todos los grupos configurados. El superusuario
    siempre pasa, igual que en el resto del dashboard.
    """

    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    grupos = settings.TRX_GRUPOS_PERMITIDOS
    if not grupos:
        return False

    return user.groups.filter(name__in=grupos).exists()


def requiere_permiso_transacciones(vista):
    """Exige sesión y permiso de Transacciones.

    `login_required` va por dentro a propósito: un anónimo recibe el 302 a
    login que ya espera el resto del dashboard, y solo un usuario
    autenticado sin rol recibe 403.

    El permiso se evalúa antes de invocar la vista, así que el camino
    denegado no arma contexto ni consulta Oracle.
    """

    @wraps(vista)
    @login_required
    def _envuelta(request, *args, **kwargs):
        if not usuario_puede_ver_transacciones(request.user):
            return HttpResponseForbidden(MENSAJE_SIN_PERMISO)

        return vista(request, *args, **kwargs)

    return _envuelta
