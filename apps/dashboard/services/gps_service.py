from datetime import timedelta
from django.utils import timezone
from ..models import EstadoValidadorLimpio, UbicacionEsperadaValidador
import math

LATITUD_LABORATORIO_ZP = -33.437191
LONGITUD_LABORATORIO_ZP = -70.656102
RADIO_LABORATORIO_ZP = 70
NOMBRE_LABORATORIO_ZP = "Laboratorio Zonas Pagas"

def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    if None in [lat1, lon1, lat2, lon2]:
        return None
    
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
                .filter(amid=amid)
                .first()
            )

            if (
                parada_esperada
                and parada_esperada.latitud_esperada is not None
                and parada_esperada.longitud_esperada is not None
                and parada_esperada.radio_metros is not None
            ):
                nombre_esperado = parada_esperada.nombre
                latitud_esperada = float(parada_esperada.latitud_esperada)
                longitud_esperada = float(parada_esperada.longitud_esperada)
                radio_metros = float(parada_esperada.radio_metros)
                operativa = parada_esperada.operativa
                origen_ubicacion = "excel"
            else:
                nombre_esperado = NOMBRE_LABORATORIO_ZP
                latitud_esperada = LATITUD_LABORATORIO_ZP
                longitud_esperada = LONGITUD_LABORATORIO_ZP
                radio_metros = RADIO_LABORATORIO_ZP
                operativa = False
                origen_ubicacion = "laboratorio_default"

            distancia = calcular_distancia_metros(
                latitud,
                longitud,
                latitud_esperada,
                longitud_esperada,
            )

            if distancia is not None:
                dentro_radio = distancia <= radio_metros

                ubicacion_esperada = {
                    "nombre": nombre_esperado,
                    "latitud": latitud_esperada,
                    "longitud": longitud_esperada,
                    "radio_metros": radio_metros,
                    "distancia_metros": round(distancia, 2),
                    "dentro_radio": dentro_radio,
                    "operativa": operativa,
                    "origen_ubicacion": origen_ubicacion,
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