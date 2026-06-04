from django.utils import timezone

from .models import EstadoValidadorLimpio


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

    return {
        "ultima_actualizacion_dashboard": ultima_actualizacion,
        "ultima_carga_datos": ultima_carga_datos,
    }