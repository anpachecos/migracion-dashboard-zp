from apps.dashboard.models import EstadoValidadorLimpio


def obtener_contexto_gps(request):
    amid = request.GET.get("amid", "").strip()

    ultimo_registro = None
    mensaje = None
    latitud = None
    longitud = None

    if amid:
        ultimo_registro = (
            EstadoValidadorLimpio.objects
            .filter(amid=amid)
            .exclude(latitud__isnull=True)
            .exclude(longitud__isnull=True)
            .order_by("-fec_estado")
            .first()
        )

        if ultimo_registro:
            latitud = float(ultimo_registro.latitud)
            longitud = float(ultimo_registro.longitud)
        else:
            mensaje = "No se encontraron coordenadas GPS para el AMID ingresado."

    return {
        "amid": amid,
        "ultimo_registro": ultimo_registro,
        "mensaje": mensaje,
        "latitud": latitud,
        "longitud": longitud,
    }