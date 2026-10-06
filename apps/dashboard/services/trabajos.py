"""Small persistent queue for generated files."""

from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.dashboard.models import TrabajoArchivo


GENERADORES = {
    "TRX_INFORME_INTERNO": "apps.transacciones.services.exportaciones_service.generar_informe_interno",
    "TRX_MAYOR_15": "apps.transacciones.services.exportaciones_service.generar_mayor_15",
    "TRX_REZAGADAS": "apps.transacciones.services.exportaciones_service.generar_rezagadas",
    "PLANTILLA_EXPORTAR": "apps.dashboard.services.trabajos.generar_exportacion_plantilla",
    "PLANTILLA_IMPORTAR": "apps.dashboard.services.trabajos.generar_importacion_plantilla",
}


def _generador(tipo):
    ruta = GENERADORES.get(tipo)
    if not ruta:
        raise ValueError(f"Tipo de trabajo no registrado: {tipo}")

    modulo, nombre = ruta.rsplit(".", 1)
    objeto = __import__(modulo, fromlist=[nombre])
    return getattr(objeto, nombre)


def crear_trabajo(usuario, tipo, parametros=None):
    if tipo not in GENERADORES:
        raise ValueError(f"Tipo de trabajo no registrado: {tipo}")

    return TrabajoArchivo.objects.create(
        usuario=usuario,
        tipo=tipo,
        parametros_json=parametros or {},
        mensaje="En cola para procesamiento.",
        fecha_expiracion=timezone.now()
        + timedelta(hours=settings.TRABAJOS_ARCHIVO_EXPIRACION_HORAS),
    )


def crear_trabajo_con_entrada(usuario, tipo, parametros, archivo):
    """Create a job and persist an uploaded input before returning."""

    trabajo = crear_trabajo(usuario, tipo, parametros)
    trabajo.archivo_entrada.save(archivo.name, archivo, save=True)
    return trabajo


def generar_exportacion_plantilla(parametros, trabajo=None):
    from apps.excel_templates import models, services
    from apps.excel_templates.options import ExportOptions

    plantilla = models.Template.objects.get(pk=parametros["plantilla_id"])
    version = None
    if parametros.get("version"):
        version = plantilla.versions.get(version_no=parametros["version"])
    exportado = services.exportar(
        plantilla,
        version=version,
        opciones=ExportOptions(keep_labels=False),
    )
    return {"contenido": exportado["datos"], "nombre": exportado["nombre"]}


def generar_importacion_plantilla(parametros, trabajo):
    from apps.excel_templates import models, services

    plantilla = None
    if parametros.get("plantilla_id"):
        plantilla = models.Template.objects.get(pk=parametros["plantilla_id"])

    resultado = services.capturar(
        trabajo.archivo_entrada.path,
        nombre=parametros.get("nombre") or None,
        descripcion=parametros.get("descripcion", ""),
        notas=parametros.get("notas", ""),
        creado_por=parametros.get("creado_por", ""),
        publicar=bool(parametros.get("publicar", True)),
        plantilla=plantilla,
    )
    version = resultado["version"]
    estado = "vigente" if version.status == models.TemplateVersion.Status.VIGENTE else "borrador"
    return {
        "contenido": None,
        "nombre": "",
        "mensaje": (
            f"Plantilla '{resultado['plantilla'].name}' importada como "
            f"versión {version.version_no} ({estado})."
        ),
    }


def tomar_siguiente_trabajo():
    """Claim one item and commit before running the generator."""

    with transaction.atomic():
        trabajo = (
            TrabajoArchivo.objects.select_for_update()
            .filter(estado=TrabajoArchivo.Estado.PENDIENTE)
            .order_by("fecha_solicitud", "pk")
            .first()
        )
        if trabajo is None:
            return None

        trabajo.estado = TrabajoArchivo.Estado.PROCESANDO
        trabajo.fecha_inicio = timezone.now()
        trabajo.progreso = 10
        trabajo.mensaje = "Generando archivo."
        trabajo.save(
            update_fields=[
                "estado",
                "fecha_inicio",
                "progreso",
                "mensaje",
            ]
        )

    return trabajo


def procesar_trabajo(trabajo):
    """Run a claimed item without an open transaction."""

    try:
        resultado = _generador(trabajo.tipo)(trabajo.parametros_json, trabajo)
        contenido = resultado.get("contenido")
        nombre = resultado.get("nombre", "")
        if contenido is not None:
            trabajo.archivo.save(nombre, ContentFile(contenido), save=False)
        trabajo.nombre_archivo = nombre
        trabajo.estado = TrabajoArchivo.Estado.LISTO
        trabajo.progreso = 100
        trabajo.mensaje = resultado.get(
            "mensaje",
            "Archivo listo para descargar.",
        )
        trabajo.error = ""
    except Exception as error:
        trabajo.estado = TrabajoArchivo.Estado.ERROR
        trabajo.progreso = 100
        trabajo.mensaje = "No se pudo generar el archivo."
        trabajo.error = str(error)
    finally:
        if trabajo.archivo_entrada:
            trabajo.archivo_entrada.delete(save=False)
            trabajo.archivo_entrada = ""
        trabajo.fecha_fin = timezone.now()
        trabajo.save(
            update_fields=[
                "archivo",
                "archivo_entrada",
                "nombre_archivo",
                "estado",
                "progreso",
                "mensaje",
                "error",
                "fecha_fin",
            ]
        )

    return trabajo


def marcar_interrumpidos():
    """A failed worker restart does not resume a partial Excel."""

    return TrabajoArchivo.objects.filter(
        estado=TrabajoArchivo.Estado.PROCESANDO
    ).update(
        estado=TrabajoArchivo.Estado.ERROR,
        fecha_fin=timezone.now(),
        progreso=100,
        mensaje="El worker fue interrumpido antes de terminar.",
        error="Proceso interrumpido por reinicio del worker.",
    )


def limpiar_expirados():
    ahora = timezone.now()
    trabajos = TrabajoArchivo.objects.filter(
        fecha_expiracion__lte=ahora
    ).exclude(
        estado__in=[
            TrabajoArchivo.Estado.PROCESANDO,
            TrabajoArchivo.Estado.EXPIRADO,
        ]
    )
    cantidad = 0
    for trabajo in trabajos.iterator():
        if trabajo.archivo_entrada:
            trabajo.archivo_entrada.delete(save=False)
        if trabajo.archivo:
            trabajo.archivo.delete(save=False)
        trabajo.estado = TrabajoArchivo.Estado.EXPIRADO
        trabajo.mensaje = "El archivo expiró y fue eliminado."
        trabajo.archivo = ""
        trabajo.archivo_entrada = ""
        trabajo.save(update_fields=["estado", "mensaje", "archivo", "archivo_entrada"])
        cantidad += 1
    return cantidad
