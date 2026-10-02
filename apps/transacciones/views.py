"""
Vistas del módulo de Transacciones.

El módulo es una sola página: las cuatro pestañas son estado del cliente y la
vista arma nada más el armazón. Los datos los pide el `dataService` del
frontend, así que acá no hay SQL ni consultas a la base.

Por lo mismo esta vista no llama a los services de informes: siguen en el
árbol porque describen la lógica real del módulo, pero el mockup lee de
`mockData.js` y no los necesita. Cuando se enchufe la base de datos, el
frontend pasa a `DATA_SOURCE = "api"` y los endpoints que hay que implementar
son los del `dataService`.

El umbral de corte se inyecta en el HTML porque las etiquetas visibles se
construyen desde `trx_reglas`, que es la única fuente donde vive ese número.
"""

from django.shortcuts import redirect, render
from django.urls import reverse

from .permisos import requiere_permiso_transacciones
from .services import trx_reglas

ACTIVE_PAGE = "transacciones"

# Las pestañas que existían antes quedaban en páginas separadas. Ahora el
# monitor es uno solo, así que cada una de esas rutas se redirige a la
# pestaña que le corresponde y los enlaces guardados siguen funcionando.
PESTANA_DE_RUTA_LEGADA = {
    "informe_interno": 0,
    "mayor_15": 2,
    "rezagadas": 3,
}


@requiere_permiso_transacciones
def monitor(request):
    return render(
        request,
        "transacciones/monitor.html",
        {
            "active_page": ACTIVE_PAGE,
            "umbral_corte_min": trx_reglas.UMBRAL_CORTE_MINUTOS,
        },
    )


@requiere_permiso_transacciones
def inicio(request):
    return redirect("transacciones:monitor")


def _redirigir_a_pestana(numero):
    return redirect(reverse("transacciones:monitor") + "?p=" + str(numero))


@requiere_permiso_transacciones
def informe_interno(request):
    return _redirigir_a_pestana(PESTANA_DE_RUTA_LEGADA["informe_interno"])


@requiere_permiso_transacciones
def mayor_15(request):
    return _redirigir_a_pestana(PESTANA_DE_RUTA_LEGADA["mayor_15"])


@requiere_permiso_transacciones
def rezagadas(request):
    return _redirigir_a_pestana(PESTANA_DE_RUTA_LEGADA["rezagadas"])