from datetime import timedelta

from django.utils import timezone

from ..models import EstadoValidadorLimpio


def obtener_contexto_gps(request):
    amid = request.GET.get("amid", "").strip()
    dias = request.GET.get("dias", "1")

    try:
        dias = int(dias)
    except ValueError:
        dias = 1

    if dias not in [1, 3, 7, 14]:
        dias = 1

    ultimo_registro = None
    mensaje = ""
    latitud = None
    longitud = None
    ubicaciones_gps = []

    if amid:
        fecha_inicio = timezone.localdate() - timedelta(days=dias - 1)

        registros = (
            EstadoValidadorLimpio.objects
            .filter(
                amid=amid,
                fecha_hora__date__gte=fecha_inicio,
            )
            .exclude(latitud__isnull=True)
            .exclude(longitud__isnull=True)
            .order_by("fecha_hora")
        )

        for registro in registros:
            try:
                lat = float(registro.latitud)
                lon = float(registro.longitud)
            except (ValueError, TypeError):
                continue

            ubicaciones_gps.append({
                "latitud": lat,
                "longitud": lon,
                "fecha_hora": timezone.localtime(registro.fecha_hora).strftime("%d-%m-%Y %H:%M") if registro.fecha_hora else "",
                "porcentaje_bateria": registro.porcentaje_bateria,
            })

        if ubicaciones_gps:
            ultima_ubicacion = ubicaciones_gps[-1]
            latitud = ultima_ubicacion["latitud"]
            longitud = ultima_ubicacion["longitud"]
            ultimo_registro = registros.last()
        else:
            mensaje = f"No se encontraron coordenadas GPS para el AMID ingresado en los últimos {dias} día{'s' if dias != 1 else ''}."

    return {
        "amid": amid,
        "dias": dias,
        "ultimo_registro": ultimo_registro,
        "mensaje": mensaje,
        "latitud": latitud,
        "longitud": longitud,
        "ubicaciones_gps": ubicaciones_gps,
    }