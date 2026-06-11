from datetime import timedelta

from django.db.models import Count, Min, Max
from django.utils import timezone

from apps.dashboard.models import EstadoValidadorLimpio, UbicacionEsperadaValidador
from apps.dashboard.services.gps_service import calcular_distancia_metros
from apps.dashboard.services.alertas_bateria_utils import (
    preparar_puntos_bateria_desde_registros,
    detectar_caidas_drasticas_desde_puntos,
)

def clasificar_gps_cero(cantidad_registros):
    if cantidad_registros >= 5:
        return "Frecuente"

    if cantidad_registros >= 2:
        return "Repetido"

    return "Aislado"

def obtener_alertas_gps_cero(dias=1, mostrar_todo=False):
    """
    Obtiene resumen de AMIDs únicos con GPS 0 dentro del período seleccionado.

    Regla:
    - latitud = 0
    - longitud = 0
    """

    try:
        dias = int(dias)
    except ValueError:
        dias = 1

    if dias not in [1, 3, 7, 14]:
        dias = 1

    fecha_inicio = timezone.now() - timedelta(days=dias)

    registros_gps_cero = (
        EstadoValidadorLimpio.objects
        .filter(
            fec_estado__gte=fecha_inicio,
            latitud=0,
            longitud=0,
        )
    )

    total_registros_gps_cero = registros_gps_cero.count()

    resumen_por_amid = (
        registros_gps_cero
        .values("amid")
        .annotate(
            cantidad_registros=Count("id"),
            primera_deteccion=Min("fec_estado"),
            ultima_deteccion=Max("fec_estado"),
        )
        .order_by("-cantidad_registros", "-ultima_deteccion")
    )

    total_amids_gps_cero = resumen_por_amid.count()

    if mostrar_todo:
        resumen_visible = list(resumen_por_amid)
    else:
        resumen_visible = list(resumen_por_amid[:5])

    for item in resumen_visible:
        ultimo_registro = (
            registros_gps_cero
            .filter(
                amid=item["amid"],
                fec_estado=item["ultima_deteccion"],
            )
            .order_by("-id")
            .first()
        )

        item["ultima_bateria"] = (
            ultimo_registro.porcentaje_bateria
            if ultimo_registro
            else None
        )

        item["estado_alerta"] = clasificar_gps_cero(
            item["cantidad_registros"]
        )

    return {
        "dias": dias,
        "total_amids_gps_cero": total_amids_gps_cero,
        "total_registros_gps_cero": total_registros_gps_cero,
        "resumen_gps_cero": resumen_visible,
        "mostrar_todo": mostrar_todo,
        "hay_mas_registros": total_amids_gps_cero > 5,
    }

def formatear_duracion(delta):
    """
    Convierte un timedelta en texto corto.
    Ejemplo: 1h 30m
    """

    total_minutos = int(delta.total_seconds() // 60)
    horas = total_minutos // 60
    minutos = total_minutos % 60

    if horas > 0:
        return f"{horas}h {minutos}m"

    return f"{minutos}m"

def obtener_alertas_caidas_bateria(
    dias=1,
    mostrar_todo=False,
    umbral_caida=30,
    ventana_horas=2
):
    """
    Detecta caídas drásticas de batería por AMID usando la lógica compartida.
    """

    try:
        dias = int(dias)
    except ValueError:
        dias = 1

    if dias not in [1, 3, 7, 14]:
        dias = 1

    fecha_inicio = timezone.now() - timedelta(days=dias)

    registros = (
        EstadoValidadorLimpio.objects
        .filter(
            fecha_hora__gte=fecha_inicio,
            porcentaje_bateria__isnull=False,
            fecha_hora__isnull=False,
        )
        .order_by("amid", "fecha_hora")
    )

    puntos = preparar_puntos_bateria_desde_registros(registros)

    eventos = detectar_caidas_drasticas_desde_puntos(
        puntos=puntos,
        umbral_caida=umbral_caida,
        ventana_horas=ventana_horas,
    )

    eventos_por_amid = {}

    for evento in eventos:
        amid = evento["amid"]
        eventos_por_amid.setdefault(amid, []).append(evento)

    resumen_caidas = []

    for amid, eventos_amid in eventos_por_amid.items():
        eventos_ordenados = sorted(
            eventos_amid,
            key=lambda evento: evento["fecha_actual"],
            reverse=True
        )

        ultima_caida = eventos_ordenados[0]
        mayor_caida = max(eventos_amid, key=lambda evento: evento["caida"])

        resumen_caidas.append({
            "amid": amid,
            "cantidad_caidas": len(eventos_amid),
            "mayor_caida": mayor_caida["caida"],
            "ultima_caida": ultima_caida["fecha_actual"],
            "bateria_anterior": ultima_caida["bateria_anterior"],
            "bateria_actual": ultima_caida["bateria_actual"],
            "tiempo_transcurrido": ultima_caida["tiempo_transcurrido"],
        })

    resumen_caidas = sorted(
        resumen_caidas,
        key=lambda item: (
            item["cantidad_caidas"],
            item["mayor_caida"],
            item["ultima_caida"],
        ),
        reverse=True
    )

    total_amids_caidas_bateria = len(resumen_caidas)
    total_eventos_caidas_bateria = sum(
        item["cantidad_caidas"] for item in resumen_caidas
    )

    if mostrar_todo:
        resumen_visible = resumen_caidas
    else:
        resumen_visible = resumen_caidas[:5]

    return {
        "total_amids_caidas_bateria": total_amids_caidas_bateria,
        "total_eventos_caidas_bateria": total_eventos_caidas_bateria,
        "resumen_caidas_bateria": resumen_visible,
        "hay_mas_caidas_bateria": total_amids_caidas_bateria > 5,
        "umbral_caida": umbral_caida,
        "ventana_horas": ventana_horas,
    }

def obtener_alertas_fuera_radio(dias=1, mostrar_todo=False):
    """
    Detecta AMIDs que tienen coordenadas válidas, distintas de 0,
    pero fuera del radio esperado definido en UbicacionEsperadaValidador.

    No considera:
    - latitud o longitud nula
    - latitud = 0 y longitud = 0
    - AMIDs sin ubicación esperada cargada
    """

    try:
        dias = int(dias)
    except ValueError:
        dias = 1

    if dias not in [1, 3, 7, 14]:
        dias = 1

    fecha_inicio = timezone.now() - timedelta(days=dias)

    ubicaciones_esperadas = {
        str(item.amid): item
        for item in UbicacionEsperadaValidador.objects.filter(
            operativa=True,
            latitud_esperada__isnull=False,
            longitud_esperada__isnull=False,
            radio_metros__isnull=False,
        )
    }

    registros = (
        EstadoValidadorLimpio.objects
        .filter(
            fecha_hora__gte=fecha_inicio,
            latitud__isnull=False,
            longitud__isnull=False,
        )
        .values(
            "amid",
            "fecha_hora",
            "fec_descarga",
            "fec_estado",
            "porcentaje_bateria",
            "latitud",
            "longitud",
        )
        .order_by("amid", "fecha_hora")
    )

    eventos_por_amid = {}

    for registro in registros:
        amid = str(registro["amid"])

        ubicacion_esperada = ubicaciones_esperadas.get(amid)

        if not ubicacion_esperada:
            continue

        try:
            latitud = float(registro["latitud"])
            longitud = float(registro["longitud"])
        except (ValueError, TypeError):
            continue

        if latitud == 0 and longitud == 0:
            continue

        distancia = calcular_distancia_metros(
            latitud,
            longitud,
            ubicacion_esperada.latitud_esperada,
            ubicacion_esperada.longitud_esperada,
        )

        if distancia is None:
            continue

        fuera_radio = distancia > ubicacion_esperada.radio_metros

        if fuera_radio:
            evento = {
                "amid": amid,
                "fecha_hora": registro["fecha_hora"],
                "fec_descarga": registro["fec_descarga"],
                "fec_estado": registro["fec_estado"],
                "porcentaje_bateria": registro["porcentaje_bateria"],
                "latitud": latitud,
                "longitud": longitud,
                "nombre_ubicacion": ubicacion_esperada.nombre,
                "radio_metros": ubicacion_esperada.radio_metros,
                "distancia_metros": round(distancia, 2),
                "exceso_metros": round(distancia - ubicacion_esperada.radio_metros, 2),
            }

            eventos_por_amid.setdefault(amid, []).append(evento)

    resumen_fuera_radio = []

    for amid, eventos in eventos_por_amid.items():
        eventos_ordenados = sorted(
            eventos,
            key=lambda evento: evento["fecha_hora"] or timezone.datetime.min.replace(tzinfo=timezone.get_current_timezone()),
            reverse=True
        )

        ultimo_evento = eventos_ordenados[0]
        mayor_distancia = max(eventos, key=lambda evento: evento["distancia_metros"])

        resumen_fuera_radio.append({
            "amid": amid,
            "cantidad_registros": len(eventos),
            "ultima_deteccion": ultimo_evento["fecha_hora"],
            "nombre_ubicacion": ultimo_evento["nombre_ubicacion"],
            "distancia_metros": ultimo_evento["distancia_metros"],
            "radio_metros": ultimo_evento["radio_metros"],
            "exceso_metros": ultimo_evento["exceso_metros"],
            "mayor_distancia": mayor_distancia["distancia_metros"],
            "ultima_bateria": ultimo_evento["porcentaje_bateria"],
        })

    resumen_fuera_radio = sorted(
        resumen_fuera_radio,
        key=lambda item: (
            item["cantidad_registros"],
            item["exceso_metros"],
            item["ultima_deteccion"],
        ),
        reverse=True
    )

    total_amids_fuera_radio = len(resumen_fuera_radio)
    total_eventos_fuera_radio = sum(
        item["cantidad_registros"] for item in resumen_fuera_radio
    )

    if mostrar_todo:
        resumen_visible = resumen_fuera_radio
    else:
        resumen_visible = resumen_fuera_radio[:5]

    return {
        "total_amids_fuera_radio": total_amids_fuera_radio,
        "total_eventos_fuera_radio": total_eventos_fuera_radio,
        "resumen_fuera_radio": resumen_visible,
        "hay_mas_fuera_radio": total_amids_fuera_radio > 5,
    }