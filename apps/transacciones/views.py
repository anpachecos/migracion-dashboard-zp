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

from apps.excel_templates import models as plantillas_models
from apps.excel_templates.permisos import usuario_puede_capturar

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
            **_contexto_de_plantillas(),
        },
    )


@requiere_permiso_transacciones
def centro_archivos(request):
    """Pantalla independiente para plantillas, reportes y actividad."""

    return render(
        request,
        "transacciones/centro_archivos.html",
        {
            "active_page": "centro_archivos",
            "umbral_corte_min": trx_reglas.UMBRAL_CORTE_MINUTOS,
            "puede_editar_plantillas": usuario_puede_capturar(request.user),
            "plantillas_admin": _plantillas_admin(request),
            **_contexto_de_plantillas(),
        },
    )


def _plantillas_admin(request):
    """Datos del panel administrativo, solo para Admin/superusuario."""

    if not usuario_puede_capturar(request.user):
        return []

    return (
        plantillas_models.Template.objects
        .select_related("current_version")
        .prefetch_related("versions")
        .order_by("name")
    )


def _contexto_de_plantillas():
    """
    Rutas de la tarjeta de plantilla Excel del monitor.

    No se pasa la lista de plantillas: la pide `plantilla.js` al abrir cada
    dialogo. Si la lista viviera en el HTML habria que recargar la pagina para
    ver el resultado de una importacion, y el boton quedaria misleading
    ("Exportar" descarga algo que el selector no lista).

    El motor vive en otra app, asi que se resuelve con `reverse` aca y no en el
    template: una etiqueta de Django no debe importar modelos de negocio.
    """

    return {
        "url_plantillas": reverse("excel_templates:listar"),
        "url_capturar": reverse("excel_templates:capturar"),
        # La ruta de exportacion se arma con un id de relleno (`0`) que el
        # navegador reemplaza por el id real de la fila que se descarga. Se
        # resuelve con `reverse` para no escribir la ruta a mano en el
        # JavaScript, asi sigue valida si cambia el prefijo en `urls.py`.
        # La descarga desde el monitor es una plantilla de formato: no debe
        # conservar textos del archivo fuente. Esta opcion queda solo en la UI;
        # la ruta/API y el comando siguen usando sus opciones normales.
        "url_exportar_base": (
            reverse("excel_templates:exportar", args=[0])
            + "?keep_labels=0"
        ),
    }


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
