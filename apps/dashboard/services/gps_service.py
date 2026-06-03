from datetime import timedelta
from django.utils import timezone
from ..models import EstadoValidadorLimpio, UbicacionEsperadaValidador
import math

def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    radio_tierra = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return radio_tierra * c

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
    ubicacion_esperada = None

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

            # Solo validamos ubicación esperada cuando el filtro es "Hoy"
            if dias == 1:
                parada_esperada = (
                    UbicacionEsperadaValidador.objects
                    .filter(amid=amid, operativa=True)
                    .first()
                )

                if parada_esperada:
                    distancia = calcular_distancia_metros(
                        latitud,
                        longitud,
                        parada_esperada.latitud_esperada,
                        parada_esperada.longitud_esperada,
                    )

                    dentro_radio = distancia <= parada_esperada.radio_metros

                    ubicacion_esperada = {
                        "nombre": parada_esperada.nombre,
                        "latitud": parada_esperada.latitud_esperada,
                        "longitud": parada_esperada.longitud_esperada,
                        "radio_metros": parada_esperada.radio_metros,
                        "distancia_metros": round(distancia, 2),
                        "dentro_radio": dentro_radio,
                    }
        else:
            mensaje = "No se encontraron coordenadas GPS para el AMID ingresado en el período seleccionado."

    return {
        "amid": amid,
        "dias": dias,
        "ultimo_registro": ultimo_registro,
        "mensaje": mensaje,
        "latitud": latitud,
        "longitud": longitud,
        "ubicaciones_gps": ubicaciones_gps,
        "ubicacion_esperada": ubicacion_esperada,
    }