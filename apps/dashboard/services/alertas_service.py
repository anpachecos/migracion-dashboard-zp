from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.dashboard.services.gps_service import calcular_distancia_metros
from apps.dashboard.services.alertas_bateria_utils import (
    preparar_puntos_bateria_desde_registros,
    detectar_caidas_drasticas_desde_puntos,
)


LATITUD_LABORATORIO_ZP = -33.437191
LONGITUD_LABORATORIO_ZP = -70.656102
RADIO_LABORATORIO_ZP = 70
NOMBRE_LABORATORIO_ZP = "Laboratorio Zonas Pagas"


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


def construir_resolvedor_referencias(amids, fecha_inicio=None):
    """
    Precarga ubicaciones vigentes e históricas para evitar consultar
    la base por cada registro de alerta.
    """

    amids = {str(amid).strip() for amid in amids if amid is not None}

    if not amids:
        def resolver_vacio(amid, fecha_consulta=None):
            return obtener_referencia_laboratorio()

        return resolver_vacio

    ubicaciones_vigentes = {
        str(item.amid): item
        for item in UbicacionEsperadaValidador.objects.filter(amid__in=amids)
    }

    historiales_qs = (
        HistorialUbicacionEsperadaValidador.objects
        .filter(amid__in=amids)
        .order_by("amid", "-fecha_inicio_vigencia")
    )

    if fecha_inicio:
        historiales_qs = historiales_qs.filter(
            Q(fecha_fin_vigencia__isnull=True)
            | Q(fecha_fin_vigencia__gte=fecha_inicio)
        )

    historiales_por_amid = {}

    for historial in historiales_qs:
        historiales_por_amid.setdefault(str(historial.amid), []).append(historial)

    def resolver(amid, fecha_consulta=None):
        amid = str(amid).strip()

        if fecha_consulta:
            for historial in historiales_por_amid.get(amid, []):
                inicio_ok = historial.fecha_inicio_vigencia <= fecha_consulta
                fin_ok = (
                    historial.fecha_fin_vigencia is None
                    or historial.fecha_fin_vigencia > fecha_consulta
                )

                if inicio_ok and fin_ok:
                    referencia = construir_referencia_desde_objeto(
                        historial,
                        origen_ubicacion=getattr(
                            historial,
                            "origen_ubicacion",
                            "historial"
                        ),
                    )

                    if referencia:
                        return referencia

        vigente = ubicaciones_vigentes.get(amid)

        referencia_vigente = construir_referencia_desde_objeto(
            vigente,
            origen_ubicacion="vigente",
        )

        if referencia_vigente:
            return referencia_vigente

        return obtener_referencia_laboratorio()

    return resolver


def obtener_referencia_esperada_por_fecha(amid, fecha_consulta=None):
    """
    Mantengo esta función por compatibilidad con otros services.
    Para alertas masivas se usa construir_resolvedor_referencias().
    """

    resolver = construir_resolvedor_referencias(
        amids=[amid],
        fecha_inicio=None,
    )

    return resolver(amid=amid, fecha_consulta=fecha_consulta)


def obtener_opciones_ubicacion_esperada():
    fecha_inicio_historial = timezone.now() - timedelta(days=14)

    nombres_vigentes = (
        UbicacionEsperadaValidador.objects
        .filter(nombre__isnull=False)
        .exclude(nombre="")
        .values_list("nombre", flat=True)
    )

    nombres_historicos = (
        HistorialUbicacionEsperadaValidador.objects
        .filter(nombre__isnull=False)
        .exclude(nombre="")
        .filter(
            Q(fecha_fin_vigencia__isnull=True)
            | Q(fecha_fin_vigencia__gte=fecha_inicio_historial)
        )
        .values_list("nombre", flat=True)
    )

    nombres = set(nombres_vigentes) | set(nombres_historicos)

    return sorted(nombres)


def clasificar_gps_cero(cantidad_registros):
    if cantidad_registros >= 5:
        return "Frecuente"

    if cantidad_registros >= 2:
        return "Repetido"

    return "Aislado"


def normalizar_dias(dias):
    try:
        dias = int(dias)
    except ValueError:
        dias = 1

    if dias not in [1, 3, 7, 14]:
        dias = 1

    return dias


def obtener_fecha_inicio_periodo(dias):
    return timezone.now() - timedelta(days=dias)


def obtener_fecha_referencia_registro(registro):
    return (
        registro.get("fecha_hora")
        or registro.get("fec_estado")
        or registro.get("fec_descarga")
    )


def obtener_alertas_gps_cero(
    dias=1,
    mostrar_todo=False,
    ubicaciones_seleccionadas=None
):
    dias = normalizar_dias(dias)
    fecha_inicio = obtener_fecha_inicio_periodo(dias)

    registros_gps_cero = (
        EstadoValidadorLimpio.objects
        .filter(
            fecha_hora__gte=fecha_inicio,
            latitud=0,
            longitud=0,
        )
        .values(
            "id",
            "amid",
            "fecha_hora",
            "fec_descarga",
            "fec_estado",
            "porcentaje_bateria",
        )
        .order_by("amid", "fecha_hora")
    )

    registros_gps_cero = list(registros_gps_cero)

    amids_periodo = {
        str(registro["amid"])
        for registro in registros_gps_cero
        if registro.get("amid") is not None
    }

    resolver_referencia = construir_resolvedor_referencias(
        amids=amids_periodo,
        fecha_inicio=fecha_inicio,
    )

    eventos_por_amid = {}

    for registro in registros_gps_cero:
        amid = str(registro["amid"])
        fecha_referencia = obtener_fecha_referencia_registro(registro)

        referencia = resolver_referencia(
            amid=amid,
            fecha_consulta=fecha_referencia,
        )

        if ubicaciones_seleccionadas is not None:
            if referencia["nombre"] not in ubicaciones_seleccionadas:
                continue

        evento = {
            "amid": amid,
            "fecha_referencia": fecha_referencia,
            "fecha_hora": registro["fecha_hora"],
            "fec_descarga": registro["fec_descarga"],
            "fec_estado": registro["fec_estado"],
            "porcentaje_bateria": registro["porcentaje_bateria"],
            "ubicacion_esperada": referencia["nombre"],
        }

        eventos_por_amid.setdefault(amid, []).append(evento)

    resumen_gps_cero = []
    total_registros_gps_cero = 0
    fecha_minima = timezone.datetime.min.replace(
        tzinfo=timezone.get_current_timezone()
    )

    for amid, eventos in eventos_por_amid.items():
        eventos_ordenados = sorted(
            eventos,
            key=lambda evento: evento["fecha_referencia"] or fecha_minima,
            reverse=True,
        )

        ultimo_evento = eventos_ordenados[0]

        fechas_validas = [
            evento["fecha_referencia"]
            for evento in eventos
            if evento["fecha_referencia"] is not None
        ]

        total_registros_gps_cero += len(eventos)

        resumen_gps_cero.append({
            "amid": amid,
            "cantidad_registros": len(eventos),
            "primera_deteccion": min(fechas_validas) if fechas_validas else None,
            "ultima_deteccion": max(fechas_validas) if fechas_validas else None,
            "ubicacion_esperada": ultimo_evento["ubicacion_esperada"] or "-",
            "ultima_bateria": ultimo_evento["porcentaje_bateria"],
            "estado_alerta": clasificar_gps_cero(len(eventos)),
        })

    resumen_gps_cero = sorted(
        resumen_gps_cero,
        key=lambda item: (
            item["cantidad_registros"],
            item["ultima_deteccion"] or fecha_minima,
        ),
        reverse=True,
    )

    total_amids_gps_cero = len(resumen_gps_cero)

    resumen_visible = resumen_gps_cero if mostrar_todo else resumen_gps_cero[:5]

    return {
        "dias": dias,
        "total_amids_gps_cero": total_amids_gps_cero,
        "total_registros_gps_cero": total_registros_gps_cero,
        "resumen_gps_cero": resumen_visible,
        "mostrar_todo": mostrar_todo,
        "hay_mas_registros": total_amids_gps_cero > 5,
    }


def obtener_alertas_caidas_bateria(
    dias=1,
    mostrar_todo=False,
    umbral_caida=30,
    ventana_horas=2
):
    dias = normalizar_dias(dias)
    fecha_inicio = obtener_fecha_inicio_periodo(dias)

    registros = (
        EstadoValidadorLimpio.objects
        .filter(
            fecha_hora__gte=fecha_inicio,
            porcentaje_bateria__isnull=False,
            fecha_hora__isnull=False,
        )
        .only(
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
            reverse=True,
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
        reverse=True,
    )

    total_amids_caidas_bateria = len(resumen_caidas)
    total_eventos_caidas_bateria = sum(
        item["cantidad_caidas"] for item in resumen_caidas
    )

    resumen_visible = resumen_caidas if mostrar_todo else resumen_caidas[:5]

    return {
        "total_amids_caidas_bateria": total_amids_caidas_bateria,
        "total_eventos_caidas_bateria": total_eventos_caidas_bateria,
        "resumen_caidas_bateria": resumen_visible,
        "hay_mas_caidas_bateria": total_amids_caidas_bateria > 5,
        "umbral_caida": umbral_caida,
        "ventana_horas": ventana_horas,
    }


def obtener_alertas_fuera_radio(
    dias=1,
    mostrar_todo=False,
    ubicaciones_seleccionadas=None
):
    dias = normalizar_dias(dias)
    fecha_inicio = obtener_fecha_inicio_periodo(dias)

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

    registros = list(registros)

    amids_periodo = {
        str(registro["amid"])
        for registro in registros
        if registro.get("amid") is not None
    }

    resolver_referencia = construir_resolvedor_referencias(
        amids=amids_periodo,
        fecha_inicio=fecha_inicio,
    )

    eventos_por_amid = {}

    for registro in registros:
        amid = str(registro["amid"])
        fecha_referencia = obtener_fecha_referencia_registro(registro)

        try:
            latitud = float(registro["latitud"])
            longitud = float(registro["longitud"])
        except (ValueError, TypeError):
            continue

        if latitud == 0 and longitud == 0:
            continue

        referencia = resolver_referencia(
            amid=amid,
            fecha_consulta=fecha_referencia,
        )

        if ubicaciones_seleccionadas is not None:
            if referencia["nombre"] not in ubicaciones_seleccionadas:
                continue

        distancia = calcular_distancia_metros(
            latitud,
            longitud,
            referencia["latitud"],
            referencia["longitud"],
        )

        if distancia is None:
            continue

        fuera_radio = distancia > referencia["radio_metros"]

        if not fuera_radio:
            continue

        evento = {
            "amid": amid,
            "fecha_hora": registro["fecha_hora"],
            "fec_descarga": registro["fec_descarga"],
            "fec_estado": registro["fec_estado"],
            "porcentaje_bateria": registro["porcentaje_bateria"],
            "latitud": latitud,
            "longitud": longitud,
            "nombre_ubicacion": referencia["nombre"],
            "radio_metros": referencia["radio_metros"],
            "distancia_metros": round(distancia, 2),
            "exceso_metros": round(distancia - referencia["radio_metros"], 2),
        }

        eventos_por_amid.setdefault(amid, []).append(evento)

    resumen_fuera_radio = []
    fecha_minima = timezone.datetime.min.replace(
        tzinfo=timezone.get_current_timezone()
    )

    for amid, eventos in eventos_por_amid.items():
        eventos_ordenados = sorted(
            eventos,
            key=lambda evento: evento["fecha_hora"] or fecha_minima,
            reverse=True,
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
            item["ultima_deteccion"] or fecha_minima,
        ),
        reverse=True,
    )

    total_amids_fuera_radio = len(resumen_fuera_radio)
    total_eventos_fuera_radio = sum(
        item["cantidad_registros"] for item in resumen_fuera_radio
    )

    resumen_visible = resumen_fuera_radio if mostrar_todo else resumen_fuera_radio[:5]

    return {
        "total_amids_fuera_radio": total_amids_fuera_radio,
        "total_eventos_fuera_radio": total_eventos_fuera_radio,
        "resumen_fuera_radio": resumen_visible,
        "hay_mas_fuera_radio": total_amids_fuera_radio > 5,
    }