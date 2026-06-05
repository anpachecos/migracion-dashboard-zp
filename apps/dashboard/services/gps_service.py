from datetime import timedelta
import math

from django.utils import timezone

from ..models import EstadoValidadorLimpio, UbicacionEsperadaValidador


LATITUD_LABORATORIO_ZP = -33.437191
LONGITUD_LABORATORIO_ZP = -70.656102
RADIO_LABORATORIO_ZP = 70
NOMBRE_LABORATORIO_ZP = "Laboratorio Zonas Pagas"


def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    if None in [lat1, lon1, lat2, lon2]:
        return None

    try:
        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)
    except (ValueError, TypeError):
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


def obtener_referencia_esperada(amid):
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
        return {
            "nombre": parada_esperada.nombre,
            "latitud": float(parada_esperada.latitud_esperada),
            "longitud": float(parada_esperada.longitud_esperada),
            "radio_metros": float(parada_esperada.radio_metros),
            "operativa": parada_esperada.operativa,
            "origen_ubicacion": "excel",
        }

    return {
        "nombre": NOMBRE_LABORATORIO_ZP,
        "latitud": LATITUD_LABORATORIO_ZP,
        "longitud": LONGITUD_LABORATORIO_ZP,
        "radio_metros": RADIO_LABORATORIO_ZP,
        "operativa": False,
        "origen_ubicacion": "laboratorio_default",
    }


def es_error_gps(registro):
    valor = getattr(registro, "is_error_obtener_gps", None)

    if valor is None:
        return False

    if isinstance(valor, bool):
        return valor

    return str(valor).strip().upper() in ["TRUE", "1", "SI", "SÍ"]


def obtener_clase_errores_gps(cantidad_errores):
    if cantidad_errores == 0:
        return "gps-estado-ok"

    if cantidad_errores <= 3:
        return "gps-estado-advertencia"

    return "gps-estado-alerta"


def obtener_clase_cumplimiento(porcentaje):
    if porcentaje is None:
        return ""

    if porcentaje >= 90:
        return "gps-estado-ok"

    if porcentaje >= 70:
        return "gps-estado-advertencia"

    return "gps-estado-alerta"


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

    resumen_gps = {
        "errores_gps_periodo": 0,
        "clase_errores_gps_periodo": "gps-estado-ok",
        "registros_hoy": 0,
        "registros_dentro_hoy": 0,
        "registros_fuera_hoy": 0,
        "porcentaje_cumplimiento_hoy": None,
        "clase_cumplimiento_hoy": "",
        "clase_ultima_ubicacion": "",
        "texto_ultima_ubicacion": "-",
    }

    if amid:
        hoy = timezone.localdate()
        fecha_inicio = hoy - timedelta(days=dias - 1)

        referencia_esperada = obtener_referencia_esperada(amid)

        registros_periodo_base = (
            EstadoValidadorLimpio.objects
            .filter(
                amid=amid,
                fecha_hora__date__gte=fecha_inicio,
            )
            .order_by("fecha_hora")
        )

        resumen_gps["errores_gps_periodo"] = sum(
            1 for registro in registros_periodo_base
            if es_error_gps(registro)
        )
        resumen_gps["clase_errores_gps_periodo"] = obtener_clase_errores_gps(
            resumen_gps["errores_gps_periodo"]
        )

        registros = (
            registros_periodo_base
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

            coordenada_cero = lat == 0 and lon == 0

            distancia = calcular_distancia_metros(
                lat,
                lon,
                referencia_esperada["latitud"],
                referencia_esperada["longitud"],
            )

            dentro_radio = None

            if distancia is not None:
                dentro_radio = distancia <= referencia_esperada["radio_metros"]

            ubicaciones_gps.append({
                "latitud": lat,
                "longitud": lon,
                "fecha_hora": timezone.localtime(registro.fecha_hora).strftime("%d-%m-%Y %H:%M") if registro.fecha_hora else "",
                "porcentaje_bateria": registro.porcentaje_bateria,
                "distancia_metros": round(distancia, 2) if distancia is not None else None,
                "dentro_radio": dentro_radio,
                "coordenada_cero": coordenada_cero,
            })

        registros_hoy = (
            EstadoValidadorLimpio.objects
            .filter(
                amid=amid,
                fecha_hora__date=hoy,
            )
            .exclude(latitud__isnull=True)
            .exclude(longitud__isnull=True)
            .order_by("fecha_hora")
        )

        for registro in registros_hoy:
            try:
                lat_hoy = float(registro.latitud)
                lon_hoy = float(registro.longitud)
            except (ValueError, TypeError):
                continue

            distancia_hoy = calcular_distancia_metros(
                lat_hoy,
                lon_hoy,
                referencia_esperada["latitud"],
                referencia_esperada["longitud"],
            )

            if distancia_hoy is None:
                continue

            resumen_gps["registros_hoy"] += 1

            if distancia_hoy <= referencia_esperada["radio_metros"]:
                resumen_gps["registros_dentro_hoy"] += 1
            else:
                resumen_gps["registros_fuera_hoy"] += 1

        if resumen_gps["registros_hoy"] > 0:
            resumen_gps["porcentaje_cumplimiento_hoy"] = round(
                resumen_gps["registros_dentro_hoy"] * 100 / resumen_gps["registros_hoy"],
                1
            )

        resumen_gps["clase_cumplimiento_hoy"] = obtener_clase_cumplimiento(
            resumen_gps["porcentaje_cumplimiento_hoy"]
        )

        if ubicaciones_gps:
            ultima_ubicacion = ubicaciones_gps[-1]
            latitud = ultima_ubicacion["latitud"]
            longitud = ultima_ubicacion["longitud"]
            ultimo_registro = registros.last()

            if ultimo_registro and ultimo_registro.fecha_hora:
                fecha_ultima_local = timezone.localtime(ultimo_registro.fecha_hora)
                resumen_gps["texto_ultima_ubicacion"] = fecha_ultima_local.strftime("%d-%m-%Y %H:%M")

                minutos_desde_ultima = (
                    timezone.localtime(timezone.now()) - fecha_ultima_local
                ).total_seconds() / 60

                if minutos_desde_ultima <= 60:
                    resumen_gps["clase_ultima_ubicacion"] = "gps-estado-ok"
                elif minutos_desde_ultima <= 180:
                    resumen_gps["clase_ultima_ubicacion"] = "gps-estado-advertencia"
                else:
                    resumen_gps["clase_ultima_ubicacion"] = "gps-estado-alerta"

            distancia_actual = calcular_distancia_metros(
                latitud,
                longitud,
                referencia_esperada["latitud"],
                referencia_esperada["longitud"],
            )

            if distancia_actual is not None:
                dentro_radio = distancia_actual <= referencia_esperada["radio_metros"]

                ubicacion_esperada = {
                    "nombre": referencia_esperada["nombre"],
                    "latitud": referencia_esperada["latitud"],
                    "longitud": referencia_esperada["longitud"],
                    "radio_metros": referencia_esperada["radio_metros"],
                    "distancia_metros": round(distancia_actual, 2),
                    "dentro_radio": dentro_radio,
                    "operativa": referencia_esperada["operativa"],
                    "origen_ubicacion": referencia_esperada["origen_ubicacion"],
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
        "resumen_gps": resumen_gps,
    }