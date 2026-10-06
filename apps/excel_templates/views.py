"""
Vistas del modulo de plantillas Excel.

Tres rutas, todas bajo el gate de Transacciones:

- `GET  plantillas/`                       lista con la version vigente de cada una.
- `GET  plantillas/<id>/exportar/`         descarga la plantilla vacia.
- `POST plantillas/capturar/`              captura un Excel.

`capturar` la dispara el boton **Importar plantilla** de la tarjeta del monitor
y exige un permiso mas estricto que las otras dos (`requiere_permiso_captura`):
crear una version nueva cambia cual es la plantilla vigente, y eso no puede
estar al alcance de quien solo tiene permiso de ver transacciones.
"""

import logging
from urllib.parse import quote

from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from . import models, services
from .permisos import requiere_permiso_captura, requiere_permiso_plantillas
from apps.dashboard.services.trabajos import crear_trabajo_con_entrada

logger = logging.getLogger(__name__)


@requiere_permiso_plantillas
@require_GET
def listar_plantillas(request):
    """
    Lista de plantillas con su version vigente.

    Devuelve solo lo que el selector necesita: id, nombre, nombre de archivo
    exportado y numero de version. La fecha de captura se incluye para que se
    vea cual se actualizo mas recientemente.
    """

    plantillas = services.listar_plantillas()

    return JsonResponse(
        {
            "plantillas": [
                {
                    "id": plantilla.id,
                    "nombre": plantilla.name,
                    "archivo": plantilla.export_filename,
                    "version": plantilla.current_version.version_no,
                    "actualizada": plantilla.updated_at.isoformat(),
                }
                for plantilla in plantillas
            ]
        }
    )


@requiere_permiso_plantillas
@require_GET
def exportar_plantilla(request, plantilla_id):
    """
    Descarga la plantilla vacia.

    Los parametros de la query (`keep_labels`, `data_rows_mode`, ...) se
    validan antes de tocar la base: una opcion invalida devuelve 400 con un
    mensaje util en vez de un error 500.
    """

    plantilla = get_object_or_404(models.Template, pk=plantilla_id)

    version = _version_solicitada(plantilla, request)

    try:
        opciones = services.opciones_desde_query(request.GET)
    except services.ErrorDePlantilla as error:
        return JsonResponse({"error": str(error)}, status=400)

    try:
        exportado = services.exportar(plantilla, version=version, opciones=opciones)
    except services.ErrorDePlantilla as error:
        return JsonResponse({"error": str(error)}, status=400)
    except Exception:
        logger.exception(
            "Error inesperado exportando plantilla '%s' v%s",
            plantilla.name,
            version.version_no,
        )
        return HttpResponse(
            "No se pudo generar el archivo Excel. Revisa el log del servidor.",
            status=500,
            content_type="text/plain; charset=utf-8",
        )

    respuesta = HttpResponse(
        exportado["datos"],
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # `attachment` fuerza la descarga con el nombre de la plantilla. El nombre
    # va en el header y no en el nombre de archivo de la vista, asi que un
    # nombre con acentos o espacios no lo rompe.
    nombre = quote(exportado["nombre"], safe="")
    # `filename` es el fallback para navegadores que no interpretan
    # `filename*`; ambos deben conservar la extension .xlsx.
    nombre_fallback = exportado["nombre"].encode("ascii", "ignore").decode()
    if not nombre_fallback.lower().endswith(".xlsx"):
        nombre_fallback = "plantilla.xlsx"
    respuesta["Content-Disposition"] = (
        f'attachment; filename="{nombre_fallback}"; '
        f"filename*=UTF-8''{nombre}"
    )
    return respuesta


@requiere_permiso_captura
@require_POST
def editar_plantilla(request, plantilla_id):
    """Edita metadatos de una plantilla sin modificar su historial."""

    plantilla = get_object_or_404(models.Template, pk=plantilla_id)

    try:
        services.editar_metadatos(
            plantilla,
            nombre=request.POST.get("nombre"),
            export_filename=request.POST.get("export_filename"),
            descripcion=request.POST.get("descripcion"),
        )
    except services.ErrorDePlantilla as error:
        return JsonResponse({"error": str(error)}, status=400)

    return HttpResponseRedirect("/transacciones/centro-archivos/?editada=1")


def _version_solicitada(plantilla, request):
    """
    Version a exportar: la vigente, o la que se pida con `?version=N`.

    Permite recuperar una version anterior sin cambiar la vigente, que es el
    mismo mecanismo que usa el rollback.
    """

    pedido = request.GET.get("version")

    if not pedido:
        if plantilla.current_version is None:
            raise services.ErrorDePlantilla(
                f"La plantilla '{plantilla.name}' todavia no tiene ninguna version "
                "capturada."
            )
        return plantilla.current_version

    try:
        numero = int(pedido)
    except (TypeError, ValueError):
        raise services.ErrorDePlantilla(
            f"El parametro 'version' debe ser un numero entero, no '{pedido}'."
        )

    version = models.TemplateVersion.objects.filter(
        template=plantilla, version_no=numero
    ).first()

    if version is None:
        raise Http404(
            f"La plantilla '{plantilla.name}' no tiene una version {numero}."
        )

    return version


@requiere_permiso_captura
@require_POST
def capturar_plantilla(request):
    """
    Captura un Excel como plantilla.

    Es la operacion que dispara el boton **Importar plantilla** del monitor de
    Transacciones. Dos formas de pedirla, segun lo que marque el dialogo:

    - `plantilla_id`: se le agrega una version nueva a esa plantilla. Es el
      caso "actualizar", y no cambia ni el nombre ni el nombre de descarga.
    - Sin `plantilla_id` y con `nombre`: crea la plantilla si no existe. Si ya
      existe una con ese nombre, la respuesta lo dice (`creada: false`) en vez
      de fallar, porque el usuario eligio un nombre y lo razonable es
      agregarle la version.

    La version queda vigente salvo que se mande `publicar=0`, que la deja en
    borrador sin mover `current_version`.
    """

    archivo = request.FILES.get("archivo")

    if archivo is None:
        return JsonResponse({"error": "Falta el archivo .xlsx o .xlsm."}, status=400)

    if not _extension_permitida(archivo.name):
        return JsonResponse(
            {"error": "Solo se aceptan archivos .xlsx o .xlsm."}, status=400
        )

    nombre = (request.POST.get("nombre") or "").strip()

    # El destino se resuelve antes de tocar el archivo: si el formulario viene
    # mal (sin destino, o con un id que no es numero), se responde 400/404 sin
    # haber guardado el upload en un temporal.
    try:
        destino = _plantilla_destino(request, nombre)
    except services.ErrorDePlantilla as error:
        return JsonResponse({"error": str(error)}, status=400)

    if request.POST.get("segundo_plano") == "1":
        trabajo = crear_trabajo_con_entrada(
            request.user,
            "PLANTILLA_IMPORTAR",
            {
                "plantilla_id": destino.pk if destino else None,
                "nombre": nombre,
                "descripcion": request.POST.get("descripcion", ""),
                "notas": request.POST.get("notas", ""),
                "creado_por": request.user.get_username(),
                "publicar": _booleano(request.POST.get("publicar"), defecto=True),
            },
            archivo,
        )
        return JsonResponse(
            {"id": trabajo.pk, "estado": trabajo.estado},
            status=202,
        )

    import tempfile

    # El archivo se guarda a disco porque `extract` lo lee por ruta, en vez de
    # cargarlo en memoria: son varios megas y asi el extractor no cambia segun
    # de donde venga el archivo.
    with tempfile.TemporaryDirectory() as temporal:
        ruta = _guardar_temporal(archivo, temporal)
        try:
            resultado = services.capturar(
                ruta,
                nombre=nombre or None,
                descripcion=request.POST.get("descripcion", ""),
                notas=request.POST.get("notas", ""),
                creado_por=request.user.get_username(),
                publicar=_booleano(request.POST.get("publicar"), defecto=True),
                plantilla=destino,
            )
        except services.ErrorDePlantillaDuplicada as error:
            # 409 y no 400: no es un dato invalido, es un archivo que ya esta
            # capturado. El modal distingue los dos casos.
            return JsonResponse(
                {"error": str(error), "codigo": "plantilla_duplicada"},
                status=409,
            )
        except services.ErrorDePlantilla as error:
            return JsonResponse({"error": str(error)}, status=400)

    plantilla = resultado["plantilla"]
    version = resultado["version"]

    return JsonResponse(
        {
            "id": plantilla.id,
            "nombre": plantilla.name,
            "archivo": plantilla.export_filename,
            "version": version.version_no,
            "vigente": version.status == models.TemplateVersion.Status.VIGENTE,
            "sha256": version.source_sha256,
            "creada": resultado.get("creada", False),
            "reporte": resultado.get("reporte"),
        }
    )


def _plantilla_destino(request, nombre):
    """
    A que plantilla se le agrega la version, segun `plantilla_id`.

    Sin `plantilla_id` devuelve `None`: la crea `services.capturar` por nombre.
    Con un id que no existe responde 404, porque un id invalido en el formulario
    no es "crear otra": es un enlace roto y conviene notarlo.
    """

    pedido = request.POST.get("plantilla_id")

    # "nueva" es el valor del radio del dialogo para crear una plantilla. El
    # JS lo elimina antes de enviar, pero aceptarlo aqui evita que una version
    # antigua del navegador falle con un error de entero.
    if not pedido or str(pedido).strip().lower() == "nueva":
        if not nombre:
            raise services.ErrorDePlantilla(
                "Elige una plantilla o escribe el nombre de una nueva."
            )
        return None

    try:
        plantilla_id = int(pedido)
    except (TypeError, ValueError):
        raise services.ErrorDePlantilla(
            f"El identificador de plantilla debe ser un numero entero, no '{pedido}'."
        )

    return get_object_or_404(models.Template, pk=plantilla_id)


def _booleano(valor, defecto):
    """Lee un booleano de formulario. Un valor raro cae al defecto."""

    if valor is None:
        return defecto

    texto = str(valor).strip().lower()

    if texto in ("", "0", "false", "no", "f"):
        return False
    if texto in ("1", "true", "yes", "si", "t"):
        return True

    return defecto


def _extension_permitida(nombre):
    return nombre.lower().endswith((".xlsx", ".xlsm"))


def _guardar_temporal(archivo, directorio):
    """Escribe el archivo subido a un directorio temporal y devuelve su ruta."""

    import os

    ruta = os.path.join(directorio, os.path.basename(archivo.name))

    with open(ruta, "wb") as destino:
        for bloque in archivo.chunks():
            destino.write(bloque)

    return ruta
