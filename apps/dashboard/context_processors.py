from django.utils import timezone

from .models import EstadoValidadorLimpio, UbicacionEsperadaValidador


def datos_actualizacion_dashboard(request):
    ultima_actualizacion = timezone.localtime(timezone.now())

    ultimo_registro = (
        EstadoValidadorLimpio.objects
        .exclude(fecha_hora__isnull=True)
        .order_by("-fecha_hora")
        .first()
    )

    ultima_carga_datos = None

    if ultimo_registro and ultimo_registro.fecha_hora:
        ultima_carga_datos = timezone.localtime(ultimo_registro.fecha_hora)

    ultima_version_zp = (
        UbicacionEsperadaValidador.objects
        .exclude(fecha_carga__isnull=True)
        .order_by("-fecha_carga")
        .first()
    )

    ultima_actualizacion_version_zp = None

    if ultima_version_zp and ultima_version_zp.fecha_carga:
        ultima_actualizacion_version_zp = timezone.localtime(ultima_version_zp.fecha_carga)

    return {
        "ultima_actualizacion_dashboard": ultima_actualizacion,
        "ultima_carga_datos": ultima_carga_datos,
        "ultima_actualizacion_version_zp": ultima_actualizacion_version_zp,
    }