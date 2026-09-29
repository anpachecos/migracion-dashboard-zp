"""
Vistas del módulo de Transacciones.

Deliberadamente pequeño: autorización, redirección, render. Sin SQL y sin
lógica de negocio. Todo el trabajo vive en `apps/transacciones/services`.

TODO(refactor): cuando exista un paquete `views/` en el dashboard, evaluar si
esta app debe adoptar la misma convención. No se hace ahora para no anticipar
una reorganización que está en curso.
"""

from django.shortcuts import redirect, render

from .permisos import requiere_permiso_transacciones
from .services.exportaciones_service import exportar_disponible
from .services.informe_interno_service import obtener_contexto_informe_interno
from .services.mayor_15_service import obtener_contexto_mayor_15
from .services.rezagadas_service import obtener_contexto_rezagadas

ACTIVE_PAGE = "transacciones"

# Las tres pestañas comparten la misma estructura de render. La única diferencia
# es qué service arma el contexto y qué template se usa.
PESTANAS = {
    "informe_interno": (
        obtener_contexto_informe_interno,
        "transacciones/informe_interno.html",
    ),
    "mayor_15": (
        obtener_contexto_mayor_15,
        "transacciones/mayor_15.html",
    ),
    "rezagadas": (
        obtener_contexto_rezagadas,
        "transacciones/rezagadas.html",
    ),
}


def _render_pestana(request, nombre):
    obtener_contexto, template = PESTANAS[nombre]

    contexto = obtener_contexto(request)
    contexto["active_page"] = ACTIVE_PAGE
    contexto["exportacion_disponible"] = exportar_disponible()

    return render(request, template, contexto)


@requiere_permiso_transacciones
def inicio(request):
    return redirect("transacciones:informe_interno")


@requiere_permiso_transacciones
def informe_interno(request):
    return _render_pestana(request, "informe_interno")


@requiere_permiso_transacciones
def mayor_15(request):
    return _render_pestana(request, "mayor_15")


@requiere_permiso_transacciones
def rezagadas(request):
    return _render_pestana(request, "rezagadas")
