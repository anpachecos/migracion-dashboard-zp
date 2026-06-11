from datetime import timedelta
import math

from django.db.models import Q
from django.utils import timezone

from ..models import (
    EstadoValidadorLimpio,
    UbicacionEsperadaValidador,
    HistorialUbicacionEsperadaValidador,
)


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


def obtener_referencia_laboratorio():
    return {
        "nombre": NOMBRE_LABORATORIO_ZP,
        "latitud": LATITUD_LABORATORIO_ZP,
        "longitud": LONGITUD_LABORATORIO_ZP,
        "radio_metros": RADIO_LABORATORIO_ZP,
        "operativa": False,
        "origen_ubicacion": "laboratorio_default",
    }


def construir_referencia_desde_objeto(objeto, origen_ubicacion):
    if (
        objeto
        and objeto.latitud_esperada is not None
        and objeto.longitud_esperada is not None
        and objeto.radio_metros is not None
    ):
        return {
            "nombre": objeto.nombre,
            "latitud": float(objeto.latitud_esperada),
            "longitud": float(objeto.longitud_esperada),
            "radio_metros": float(objeto.radio_metros),
            "operativa": objeto.operativa,
            "origen_ubicacion": origen_ubicacion,
        }

    return None


def obtener_referencia_esperada(amid, fecha_consulta=None):
    """
    Obtiene la ubicación esperada del AMID.

    - Si viene fecha_consulta, busca en el historial la ubicación vigente en esa fecha.
    - Si no encuentra historial, usa la tabla vigente.
    - Si tampoco encuentra vigente, usa Laboratorio Zonas Pagas.
    """

    amid = str(amid).strip()

    if fecha_consulta:
        historial = (
            HistorialUbicacionEsperadaValidador.objects
            .filter(
                amid=amid,
                fecha_inicio_vigencia__lte=fecha_consulta,
            )
            .filter(
                Q(fecha_fin_vigencia__isnull=True)
                | Q(fecha_fin_vigencia__gt=fecha_consulta)
            )
            .order_by("-fecha_inicio_vigencia")
            .first()
        )

        referencia_historial = construir_referencia_desde_objeto(
            historial,
            origen_ubicacion=getattr(historial, "origen_ubicacion", "historial") if historial else "historial",
        )

        if referencia_historial:
            return referencia_historial

    parada_esperada = (
        UbicacionEsperadaValidador.objects
        .filter(amid=amid)
        .first()
    )

    referencia_vigente = construir_referencia_desde_objeto(
        parada_esperada,
        origen_ubicacion="vigente",
    )

    if referencia_vigente:
        return referencia_vigente

    return obtener_referencia_laboratorio()


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


def obtener_textos_periodo(dias):
    if dias == 1:
        return {
            "texto_periodo": "Hoy",
            "texto_cumplimiento": "Cumplimiento hoy",
            "texto_dentro": "Dentro hoy",
            "texto_fuera": "Fuera hoy",
        }

    return {
        "texto_periodo": f"Últimos {dias} días",
        "texto_cumplimiento": f"Cumplimiento {dias} días",
        "texto_dentro": f"Dentro {dias} días",
        "texto_fuera": f"Fuera {dias} días",
    }


def crear_resumen_gps(dias):
    textos_periodo = obtener_textos_periodo(dias)

    return {
        "errores_gps_periodo": 0,
        "clase_errores_gps_periodo": "gps-estado-ok",

        "registros_periodo": 0,
        "registros_dentro_periodo": 0,
        "registros_fuera_periodo": 0,
        "porcentaje_cumplimiento_periodo": None,
        "clase_cumplimiento_periodo": "",

        "texto_periodo": textos_periodo["texto_periodo"],
        "texto_cumplimiento": textos_periodo["texto_cumplimiento"],
        "texto_dentro": textos_periodo["texto_dentro"],
        "texto_fuera": textos_periodo["texto_fuera"],

        "clase_ultima_ubicacion": "",
        "texto_ultima_ubicacion": "-",
    }


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

    ubicacion_laboratorio = {
        "nombre": NOMBRE_LABORATORIO_ZP,
        "latitud": LATITUD_LABORATORIO_ZP,
        "longitud": LONGITUD_LABORATORIO_ZP,
        "radio_metros": RADIO_LABORATORIO_ZP,
    }

    resumen_gps = crear_resumen_gps(dias)

    if amid:
        hoy = timezone.localdate()
        fecha_inicio = hoy - timedelta(days=dias - 1)

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

            referencia_esperada = obtener_referencia_esperada(
                amid=amid,
                fecha_consulta=registro.fecha_hora,
            )

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

            if distancia is not None:
                resumen_gps["registros_periodo"] += 1

                if dentro_radio:
                    resumen_gps["registros_dentro_periodo"] += 1
                else:
                    resumen_gps["registros_fuera_periodo"] += 1

            ubicaciones_gps.append({
                "latitud": lat,
                "longitud": lon,
                "fecha_hora": timezone.localtime(registro.fecha_hora).strftime("%d-%m-%Y %H:%M") if registro.fecha_hora else "",
                "porcentaje_bateria": registro.porcentaje_bateria,
                "distancia_metros": round(distancia, 2) if distancia is not None else None,
                "dentro_radio": dentro_radio,
                "coordenada_cero": coordenada_cero,
                "ubicacion_esperada_nombre": referencia_esperada["nombre"],
            })

        if resumen_gps["registros_periodo"] > 0:
            resumen_gps["porcentaje_cumplimiento_periodo"] = round(
                resumen_gps["registros_dentro_periodo"] * 100 / resumen_gps["registros_periodo"],
                1
            )

        resumen_gps["clase_cumplimiento_periodo"] = obtener_clase_cumplimiento(
            resumen_gps["porcentaje_cumplimiento_periodo"]
        )

        if ubicaciones_gps:
            ultima_ubicacion = ubicaciones_gps[-1]
            latitud = ultima_ubicacion["latitud"]
            longitud = ultima_ubicacion["longitud"]
            ultimo_registro = registros.last()

            fecha_ultima_referencia = None

            if ultimo_registro and ultimo_registro.fecha_hora:
                fecha_ultima_referencia = ultimo_registro.fecha_hora
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

            referencia_actual = obtener_referencia_esperada(
                amid=amid,
                fecha_consulta=fecha_ultima_referencia,
            )

            distancia_actual = calcular_distancia_metros(
                latitud,
                longitud,
                referencia_actual["latitud"],
                referencia_actual["longitud"],
            )

            if distancia_actual is not None:
                dentro_radio = distancia_actual <= referencia_actual["radio_metros"]

                ubicacion_esperada = {
                    "nombre": referencia_actual["nombre"],
                    "latitud": referencia_actual["latitud"],
                    "longitud": referencia_actual["longitud"],
                    "radio_metros": referencia_actual["radio_metros"],
                    "distancia_metros": round(distancia_actual, 2),
                    "dentro_radio": dentro_radio,
                    "operativa": referencia_actual["operativa"],
                    "origen_ubicacion": referencia_actual["origen_ubicacion"],
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
        "ubicacion_laboratorio": ubicacion_laboratorio,
        "resumen_gps": resumen_gps,
    }