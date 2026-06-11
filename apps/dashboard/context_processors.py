from django.utils import timezone
from django.db.models import Max

from .models import EstadoValidadorLimpio, UbicacionEsperadaValidador


def datos_actualizacion_dashboard(request):
    ultima_actualizacion = timezone.localtime(timezone.now())

    ultima_carga_datos = None
    ultima_actualizacion_version_zp = None

    try:
        ultima_fecha = EstadoValidadorLimpio.objects.aggregate(
            ultima=Max("fecha_hora")
        )["ultima"]

        if ultima_fecha:
            ultima_carga_datos = timezone.localtime(ultima_fecha)

        ultima_version = UbicacionEsperadaValidador.objects.aggregate(
            ultima=Max("fecha_carga")
        )["ultima"]

        if ultima_version:
            ultima_actualizacion_version_zp = timezone.localtime(ultima_version)

    except Exception:
        pass

    return {
        "ultima_actualizacion_dashboard": ultima_actualizacion,
        "ultima_carga_datos": ultima_carga_datos,
        "ultima_actualizacion_version_zp": ultima_actualizacion_version_zp,
    }