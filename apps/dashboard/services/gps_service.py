from datetime import datetime, time, timedelta
from types import SimpleNamespace
import math

from apps.dashboard.repositories import gps_repository
from apps.dashboard.services.horarios_zp_service import (
    crear_configuracion_horario_zp,
    filtrar_registros_por_horario_zp,
    generar_bloques_media_hora,
)
from apps.dashboard.services.normalizacion import (
    es_coordenada_cero,
    normalizar_booleano_oracle,
    normalizar_fecha_para_comparar,
    obtener_ahora_referencia,
)


LATITUD_LABORATORIO_ZP = -33.437191
LONGITUD_LABORATORIO_ZP = -70.656102
RADIO_LABORATORIO_ZP = 150
NOMBRE_LABORATORIO_ZP = "Laboratorio Zonas Pagas"


def fecha_a_texto_oracle(fecha):
    fecha = normalizar_fecha_para_comparar(fecha)

    if not fecha:
        return None

    return fecha.strftime("%Y-%m-%d %H:%M:%S")


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
        "version_zp": None,
        "archivo_origen": None,
    }


def construir_referencia_desde_fila(fila, origen_ubicacion):
    if not fila:
        return None

    latitud = fila.get("LATITUD_ESPERADA")
    longitud = fila.get("LONGITUD_ESPERADA")
    radio = fila.get("RADIO_METROS")

    if latitud is None or longitud is None or radio is None:
        return None

    try:
        return {
            "nombre": fila.get("NOMBRE") or NOMBRE_LABORATORIO_ZP,
            "latitud": float(latitud),
            "longitud": float(longitud),
            "radio_metros": float(radio),
            "operativa": normalizar_booleano_oracle(fila.get("OPERATIVA")),
            "origen_ubicacion": fila.get("ORIGEN_UBICACION") or origen_ubicacion,
            "version_zp": fila.get("VERSION_ZP"),
            "archivo_origen": fila.get("ARCHIVO_ORIGEN"),
        }
    except (ValueError, TypeError):
        return None


def obtener_rango_fechas_gps(request):
    """
    Lee filtros de fecha/hora desde GET.

    Por defecto:
    hoy 00:00 hasta hoy 23:30.

    Internamente fecha_fin_query suma 30 minutos para incluir
    el último bloque seleccionado.
    """

    hoy = obtener_ahora_referencia().date()

    fecha_desde_texto = request.GET.get("fecha_desde", "")
    fecha_hasta_texto = request.GET.get("fecha_hasta", "")
    hora_desde = request.GET.get("hora_desde", "00:00")
    hora_hasta = request.GET.get("hora_hasta", "23:30")

    bloques_validos = generar_bloques_media_hora()

    if hora_desde not in bloques_validos:
        hora_desde = "00:00"

    if hora_hasta not in bloques_validos:
        hora_hasta = "23:30"

    try:
        fecha_desde = datetime.strptime(fecha_desde_texto, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        fecha_desde = hoy

    try:
        fecha_hasta = datetime.strptime(fecha_hasta_texto, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        fecha_hasta = hoy

    hora_desde_obj = datetime.strptime(hora_desde, "%H:%M").time()
    hora_hasta_obj = datetime.strptime(hora_hasta, "%H:%M").time()

    fecha_inicio = datetime.combine(fecha_desde, hora_desde_obj)
    fecha_fin_bloque = datetime.combine(fecha_hasta, hora_hasta_obj)

    if fecha_inicio > fecha_fin_bloque:
        fecha_desde = hoy
        fecha_hasta = hoy
        hora_desde = "00:00"
        hora_hasta = "23:30"
        fecha_inicio = datetime.combine(hoy, time.min)
        fecha_fin_bloque = datetime.combine(hoy, time(hour=23, minute=30))

    fecha_fin_query = fecha_fin_bloque + timedelta(minutes=30)

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "fecha_desde_input": fecha_desde.strftime("%Y-%m-%d"),
        "fecha_hasta_input": fecha_hasta.strftime("%Y-%m-%d"),
        "hora_desde": hora_desde,
        "hora_hasta": hora_hasta,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin_query,
        "bloques_horarios": bloques_validos,
    }


def obtener_registros_gps_oracle(amid, fecha_inicio, fecha_fin):
    """
    Obtiene los bloques creados en Oracle dentro del rango solicitado.

    FECHA_REGISTRO representa la hora del bloque. FECHA_HORA es la hora
    reportada por el validador: si se repite respecto del bloque anterior,
    el equipo no transmitió un GPS nuevo y las coordenadas se normalizan a NULL.
    """

    resultado = gps_repository.obtener_registros_gps(
        amid=amid,
        fecha_inicio=fecha_a_texto_oracle(fecha_inicio),
        fecha_fin=fecha_a_texto_oracle(fecha_fin),
    )
    registros = []
    fecha_hora_anterior = normalizar_fecha_para_comparar(
        resultado.get("fecha_hora_anterior")
    )

    for datos in resultado["registros"]:
        fecha_hora_validador = normalizar_fecha_para_comparar(
            datos.get("fecha_hora")
        )
        transmitio_gps = (
            fecha_hora_validador is not None
            and fecha_hora_validador != fecha_hora_anterior
        )

        registros.append(
            SimpleNamespace(
                id=datos.get("id"),
                amid=datos.get("amid"),
                fec_descarga=normalizar_fecha_para_comparar(datos.get("fec_descarga")),
                fec_estado=normalizar_fecha_para_comparar(datos.get("fec_estado")),
                fecha_hora=fecha_hora_validador,
                fecha_registro=normalizar_fecha_para_comparar(datos.get("fecha_registro")),
                fecha_hora_anterior=fecha_hora_anterior,
                transmitio_gps=transmitio_gps,
                latitud=datos.get("latitud") if transmitio_gps else None,
                longitud=datos.get("longitud") if transmitio_gps else None,
                porcentaje_bateria=datos.get("porcentaje_bateria"),
                is_contiene_gps=normalizar_booleano_oracle(datos.get("is_contiene_gps")),
                is_error_obtener_gps=normalizar_booleano_oracle(datos.get("is_error_obtener_gps")),
            )
        )

        if fecha_hora_validador is not None:
            fecha_hora_anterior = fecha_hora_validador

    return registros


def gps_tiene_coordenadas(registro):
    """
    Indica si el registro tiene latitud/longitud informadas.
    Incluye 0,0 porque igual es un dato reportado, aunque sea inválido.
    """

    return registro.latitud is not None and registro.longitud is not None


def gps_es_coordenada_cero(registro):
    """
    True cuando el registro reportó latitud/longitud 0,0.
    """
    return es_coordenada_cero(registro.latitud, registro.longitud)


def gps_tiene_coordenadas_validas_no_cero(registro):
    """
    Indica si el registro tiene coordenadas GPS útiles.

    Excluye 0,0 porque no representa una ubicación real.
    """

    if registro.latitud is None or registro.longitud is None:
        return False

    try:
        latitud = float(registro.latitud)
        longitud = float(registro.longitud)
    except (ValueError, TypeError):
        return False

    return not (latitud == 0 and longitud == 0)


def filtros_gps_son_por_defecto(request, filtros_fecha=None):
    """
    True cuando la búsqueda NO viene marcada como rango manual.

    Regla del panel:
    - rango_manual = 0: intentar hoy y, si no hay GPS reportado, usar último día disponible.
    - rango_manual = 1: respetar estrictamente fecha/hora elegida por el usuario.
    """

    return request.GET.get("rango_manual", "0") != "1"


def construir_filtros_gps_para_dia(fecha_objetivo):
    """
    Construye estructura de filtros para un día completo.
    Se usa para mostrar el último día con GPS disponible.
    """

    bloques_validos = generar_bloques_media_hora()

    fecha_inicio = datetime.combine(fecha_objetivo, time.min)
    fecha_fin_bloque = datetime.combine(fecha_objetivo, time(hour=23, minute=30))
    fecha_fin_query = fecha_fin_bloque + timedelta(minutes=30)

    return {
        "fecha_desde": fecha_objetivo,
        "fecha_hasta": fecha_objetivo,
        "fecha_desde_input": fecha_objetivo.strftime("%Y-%m-%d"),
        "fecha_hasta_input": fecha_objetivo.strftime("%Y-%m-%d"),
        "hora_desde": "00:00",
        "hora_hasta": "23:30",
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin_query,
        "bloques_horarios": bloques_validos,
    }


def obtener_ultimo_registro_gps_valido_oracle(amid):
    """
    Busca el último registro GPS útil del AMID, sin considerar coordenada 0,0.
    """

    datos = gps_repository.obtener_ultimo_registro_gps_valido(amid)
    if not datos:
        return None

    return SimpleNamespace(
        id=datos.get("id"),
        amid=datos.get("amid"),
        fec_descarga=normalizar_fecha_para_comparar(datos.get("fec_descarga")),
        fec_estado=normalizar_fecha_para_comparar(datos.get("fec_estado")),
        fecha_hora=normalizar_fecha_para_comparar(datos.get("fecha_hora")),
        latitud=datos.get("latitud"),
        longitud=datos.get("longitud"),
        porcentaje_bateria=datos.get("porcentaje_bateria"),
        is_contiene_gps=normalizar_booleano_oracle(datos.get("is_contiene_gps")),
        is_error_obtener_gps=normalizar_booleano_oracle(datos.get("is_error_obtener_gps")),
    )


def normalizar_historial_ubicacion_amid(historial):
    """
    Normaliza las fechas del historial obtenido desde el repositorio.
    """
    for datos in historial:
        datos["FECHA_INICIO_VIGENCIA"] = normalizar_fecha_para_comparar(
            datos.get("FECHA_INICIO_VIGENCIA")
        )
        datos["FECHA_FIN_VIGENCIA"] = normalizar_fecha_para_comparar(
            datos.get("FECHA_FIN_VIGENCIA")
        )

    return historial


def normalizar_ubicacion_vigente_amid(datos):
    """
    Identifica como vigente la ubicación obtenida desde el repositorio.
    """
    if not datos:
        return None

    datos["ORIGEN_UBICACION"] = "vigente"

    return datos


def obtener_datos_ubicacion_amid_oracle(amid):
    """Obtiene y normaliza historial y ubicación vigente de un AMID."""
    resultado = gps_repository.obtener_datos_ubicacion_amid(amid)
    historial = normalizar_historial_ubicacion_amid(resultado["historial"])
    vigente = normalizar_ubicacion_vigente_amid(resultado["vigente"])
    return historial, vigente


def obtener_referencia_desde_cache(fecha_consulta, historial_amid, vigente_amid):
    """
    Busca la referencia esperada usando datos ya cargados en memoria.

    Prioridad:
    1. Historial vigente en la fecha del registro GPS.
    2. Ubicación vigente actual.
    3. Laboratorio por defecto.
    """

    fecha_consulta = normalizar_fecha_para_comparar(fecha_consulta)

    if fecha_consulta:
        for item in reversed(historial_amid):
            fecha_inicio = item.get("FECHA_INICIO_VIGENCIA")
            fecha_fin = item.get("FECHA_FIN_VIGENCIA")

            if not fecha_inicio:
                continue

            vigente_en_fecha = (
                fecha_inicio <= fecha_consulta
                and (
                    fecha_fin is None
                    or fecha_fin > fecha_consulta
                )
            )

            if vigente_en_fecha:
                referencia = construir_referencia_desde_fila(
                    item,
                    origen_ubicacion=item.get("ORIGEN_UBICACION") or "historial",
                )

                if referencia:
                    return referencia

    referencia_vigente = construir_referencia_desde_fila(
        vigente_amid,
        origen_ubicacion="vigente",
    )

    if referencia_vigente:
        return referencia_vigente

    return obtener_referencia_laboratorio()


def es_error_gps(registro):
    valor = getattr(registro, "is_error_obtener_gps", None)
    return normalizar_booleano_oracle(valor)


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


def crear_resumen_gps_rango(fecha_desde, fecha_hasta, hora_desde, hora_hasta):
    if fecha_desde == fecha_hasta:
        texto_fechas_periodo = fecha_desde.strftime("%d-%m-%Y")
        texto_periodo = f"{texto_fechas_periodo} {hora_desde} a {hora_hasta}"
    else:
        texto_fechas_periodo = (
            f"{fecha_desde.strftime('%d-%m-%Y')} "
            f"al {fecha_hasta.strftime('%d-%m-%Y')}"
        )
        texto_periodo = (
            f"{fecha_desde.strftime('%d-%m-%Y')} {hora_desde} "
            f"a {fecha_hasta.strftime('%d-%m-%Y')} {hora_hasta}"
        )

    texto_horario_periodo = f"Desde {hora_desde} hasta {hora_hasta}"

    return {
        "errores_gps_periodo": 0,
        "clase_errores_gps_periodo": "gps-estado-ok",

        # Base de cumplimiento:
        # toda transmisión GPS, incluyendo 0,0.
        # Los bloques sin transmisión se informan por separado y no forman
        # parte del denominador.
        "registros_periodo": 0,
        "registros_dentro_periodo": 0,
        "registros_fuera_periodo": 0,

        # Resumen informativo.
        "registros_totales_periodo": 0,
        "registros_gps_reportados_periodo": 0,
        "registros_gps_validos_periodo": 0,
        "registros_sin_transmision_periodo": 0,
        "registros_gps_cero_periodo": 0,

        "porcentaje_cumplimiento_periodo": None,
        "clase_cumplimiento_periodo": "",

        "texto_periodo": texto_periodo,
        "texto_fechas_periodo": texto_fechas_periodo,
        "texto_horario_periodo": texto_horario_periodo,
        "texto_cumplimiento": "Cumplimiento período",
        "texto_dentro": "Dentro período",
        "texto_fuera": "Fuera período",

        "clase_ultima_ubicacion": "",
        "texto_ultima_ubicacion": "-",
        "texto_tiempo_desde_ultima": "",
    }


def _armar_resumen_amid_gps(estado):
    """
    Consulta los bloques GPS del AMID y aplica el fallback al último día reportado
    cuando no hubo coordenadas GPS hoy.
    """
    try:
        registros_periodo_base = obtener_registros_gps_oracle(
            amid=estado.amid,
            fecha_inicio=estado.filtros_fecha["fecha_inicio"],
            fecha_fin=estado.filtros_fecha["fecha_fin"],
        )

        registros_reportados_inicial = [
            registro for registro in registros_periodo_base
            if gps_tiene_coordenadas(registro)
        ]

        # Fallback:
        # Solo buscamos el último día si NO hubo GPS reportado hoy.
        # Si hubo 0,0 hoy, se muestra hoy y se cuenta como fuera.
        if estado.filtros_por_defecto and not registros_reportados_inicial:
            ultimo_gps_valido = obtener_ultimo_registro_gps_valido_oracle(estado.amid)

            if ultimo_gps_valido and ultimo_gps_valido.fecha_hora:
                fecha_ultimo_dia_reportado = ultimo_gps_valido.fecha_hora.date()
                estado.filtros_fecha = construir_filtros_gps_para_dia(
                    fecha_ultimo_dia_reportado
                )

                registros_periodo_base = obtener_registros_gps_oracle(
                    amid=estado.amid,
                    fecha_inicio=estado.filtros_fecha["fecha_inicio"],
                    fecha_fin=estado.filtros_fecha["fecha_fin"],
                )

                estado.usando_ultimo_dia_reportado = True
                estado.rango_manual = "0"
                estado.fecha_ultimo_dia_reportado = fecha_ultimo_dia_reportado

                estado.resumen_gps = crear_resumen_gps_rango(
                    fecha_desde=estado.filtros_fecha["fecha_desde"],
                    fecha_hasta=estado.filtros_fecha["fecha_hasta"],
                    hora_desde=estado.filtros_fecha["hora_desde"],
                    hora_hasta=estado.filtros_fecha["hora_hasta"],
                )

                estado.mensaje = (
                    "El AMID no envió coordenadas GPS hoy. "
                    "Se muestran las últimas coordenadas válidas disponibles "
                    f"del {fecha_ultimo_dia_reportado.strftime('%d-%m-%Y')}."
                )
    except ValueError:
        estado.mensaje = "El AMID ingresado no es válido."
        registros_periodo_base = []
    except Exception as error:
        estado.mensaje = f"Error consultando datos GPS en Oracle: {error}"
        registros_periodo_base = []

    estado.registros_periodo_base = registros_periodo_base


def _armar_ubicacion_y_horario_gps(estado):
    """
    Recupera la ubicación esperada del AMID y aplica el filtro por horario ZP
    cuando fue solicitado y existe horario vigente para hoy.
    """
    try:
        estado.historial_amid, estado.vigente_amid = (
            obtener_datos_ubicacion_amid_oracle(estado.amid)
        )

        estado.horario_zp = crear_configuracion_horario_zp(
            datos=estado.vigente_amid,
            fecha_referencia=obtener_ahora_referencia(),
        )
    except Exception as error:
        estado.aviso_horario_zp = (
            "No fue posible consultar el horario vigente; "
            "los registros se mantienen sin filtro."
        )
        if not estado.mensaje:
            estado.mensaje = f"Error consultando ubicación esperada en Oracle: {error}"

    if estado.horario_zp_solicitado and not estado.horario_zp["tiene_horario_hoy"]:
        estado.horario_zp_solicitado = False

    if estado.horario_zp_solicitado and estado.horario_zp["tiene_horario_hoy"]:
        estado.registros_periodo_base, estado.horario_zp_activo = (
            filtrar_registros_por_horario_zp(
                registros=estado.registros_periodo_base,
                configuracion=estado.horario_zp,
                atributo_fecha="fecha_registro",
            )
        )


def _armar_detalle_periodo_gps(estado):
    """
    Construye mapa, historial, resumen de cumplimiento y última ubicación
    a partir de los bloques ya filtrados del AMID.
    """
    registros_periodo_base = estado.registros_periodo_base

    estado.resumen_gps["registros_totales_periodo"] = len(registros_periodo_base)

    estado.resumen_gps["errores_gps_periodo"] = sum(
        1 for registro in registros_periodo_base
        if es_error_gps(registro)
    )

    estado.resumen_gps["clase_errores_gps_periodo"] = obtener_clase_errores_gps(
        estado.resumen_gps["errores_gps_periodo"]
    )

    registros_reportados = [
        registro for registro in registros_periodo_base
        if gps_tiene_coordenadas(registro)
    ]

    registros_validos = [
        registro for registro in registros_periodo_base
        if gps_tiene_coordenadas_validas_no_cero(registro)
    ]

    registros_sin_transmision = [
        registro for registro in registros_periodo_base
        if registro.transmitio_gps is False
    ]

    registros_cero = [
        registro for registro in registros_periodo_base
        if gps_es_coordenada_cero(registro)
    ]

    estado.resumen_gps["registros_gps_reportados_periodo"] = len(registros_reportados)
    estado.resumen_gps["registros_gps_validos_periodo"] = len(registros_validos)
    estado.resumen_gps["registros_sin_transmision_periodo"] = len(
        registros_sin_transmision
    )
    estado.resumen_gps["registros_gps_cero_periodo"] = len(registros_cero)

    try:
        ultima_ubicacion_reportada = None
        ultimo_registro_reportado = None
        ultima_ubicacion_valida = None
        ultimo_registro_valido = None
        ubicaciones_mapa_por_id = {}

        for registro in registros_reportados:
            try:
                lat = float(registro.latitud)
                lon = float(registro.longitud)
            except (ValueError, TypeError):
                continue

            referencia_esperada = obtener_referencia_desde_cache(
                fecha_consulta=registro.fecha_registro or registro.fecha_hora,
                historial_amid=estado.historial_amid,
                vigente_amid=estado.vigente_amid,
            )

            coordenada_cero = lat == 0 and lon == 0

            if coordenada_cero:
                distancia = None
                dentro_radio = None
                estado.resumen_gps["registros_periodo"] += 1
            else:
                distancia = calcular_distancia_metros(
                    lat,
                    lon,
                    referencia_esperada["latitud"],
                    referencia_esperada["longitud"],
                )

                dentro_radio = None

                if distancia is not None:
                    dentro_radio = distancia <= referencia_esperada["radio_metros"]

                    estado.resumen_gps["registros_periodo"] += 1

                    if dentro_radio:
                        estado.resumen_gps["registros_dentro_periodo"] += 1
                    else:
                        estado.resumen_gps["registros_fuera_periodo"] += 1

            ubicacion_mapa = {
                "id": registro.id,
                "latitud": lat,
                "longitud": lon,
                "fecha_hora": registro.fecha_hora.strftime("%d-%m-%Y %H:%M") if registro.fecha_hora else "",
                "fecha_registro": registro.fecha_registro.strftime("%d-%m-%Y %H:%M") if registro.fecha_registro else "",
                "fecha_hora_validador": registro.fecha_hora.strftime("%d-%m-%Y %H:%M") if registro.fecha_hora else "",
                "transmitio_gps": True,
                "porcentaje_bateria": registro.porcentaje_bateria,
                "distancia_metros": round(distancia, 2) if distancia is not None else None,
                "dentro_radio": dentro_radio,
                "coordenada_cero": coordenada_cero,
                "ubicacion_esperada_nombre": referencia_esperada["nombre"],
                "ubicacion_esperada_latitud": referencia_esperada["latitud"],
                "ubicacion_esperada_longitud": referencia_esperada["longitud"],
                "ubicacion_esperada_radio_metros": referencia_esperada["radio_metros"],
                "ubicacion_esperada_version": referencia_esperada.get("version_zp"),
                "indice_mapa": len(estado.ubicaciones_gps),
            }

            estado.ubicaciones_gps.append(ubicacion_mapa)
            ubicaciones_mapa_por_id[str(registro.id)] = ubicacion_mapa

            ultima_ubicacion_reportada = ubicacion_mapa
            ultimo_registro_reportado = registro

            if not coordenada_cero:
                ultima_ubicacion_valida = ubicacion_mapa
                ultimo_registro_valido = registro

        # El historial representa bloques, no solo puntos del mapa.
        # FECHA_REGISTRO identifica el bloque; una FECHA_HORA repetida indica
        # que el validador no transmitió coordenadas nuevas en ese bloque.
        for registro in registros_periodo_base:
            ubicacion_transmitida = ubicaciones_mapa_por_id.get(str(registro.id))

            if ubicacion_transmitida is not None:
                estado.historial_gps.append(ubicacion_transmitida)
                continue

            referencia_esperada = obtener_referencia_desde_cache(
                fecha_consulta=registro.fecha_registro or registro.fecha_hora,
                historial_amid=estado.historial_amid,
                vigente_amid=estado.vigente_amid,
            )

            estado.historial_gps.append({
                "id": registro.id,
                "latitud": None,
                "longitud": None,
                "fecha_hora": registro.fecha_hora.strftime("%d-%m-%Y %H:%M") if registro.fecha_hora else "",
                "fecha_registro": registro.fecha_registro.strftime("%d-%m-%Y %H:%M") if registro.fecha_registro else "",
                "fecha_hora_validador": registro.fecha_hora.strftime("%d-%m-%Y %H:%M") if registro.fecha_hora else "",
                "transmitio_gps": registro.transmitio_gps,
                "porcentaje_bateria": (
                    registro.porcentaje_bateria
                    if registro.transmitio_gps
                    else None
                ),
                "distancia_metros": None,
                "dentro_radio": None,
                "coordenada_cero": False,
                "ubicacion_esperada_nombre": referencia_esperada["nombre"],
                "ubicacion_esperada_latitud": referencia_esperada["latitud"],
                "ubicacion_esperada_longitud": referencia_esperada["longitud"],
                "ubicacion_esperada_radio_metros": referencia_esperada["radio_metros"],
                "ubicacion_esperada_version": referencia_esperada.get("version_zp"),
                "indice_mapa": None,
            })

        if estado.resumen_gps["registros_periodo"] > 0:
            estado.resumen_gps["porcentaje_cumplimiento_periodo"] = round(
                estado.resumen_gps["registros_dentro_periodo"] * 100 / estado.resumen_gps["registros_periodo"],
                1
            )

        estado.resumen_gps["clase_cumplimiento_periodo"] = obtener_clase_cumplimiento(
            estado.resumen_gps["porcentaje_cumplimiento_periodo"]
        )

        # Para centrar el mapa usamos la última coordenada válida.
        # Si solo hay 0,0, no centramos en 0,0.
        if ultima_ubicacion_valida:
            estado.latitud = ultima_ubicacion_valida["latitud"]
            estado.longitud = ultima_ubicacion_valida["longitud"]

        # Para estado y última ubicación usamos la última coordenada reportada.
        if ultimo_registro_reportado:
            estado.ultimo_registro = ultimo_registro_reportado
            fecha_ultima_referencia = (
                ultimo_registro_reportado.fecha_registro
                or ultimo_registro_reportado.fecha_hora
            )
        else:
            fecha_ultima_referencia = None

        if estado.ultimo_registro and (
            estado.ultimo_registro.fecha_registro or estado.ultimo_registro.fecha_hora
        ):
            fecha_ultima_transmision = (
                estado.ultimo_registro.fecha_registro or estado.ultimo_registro.fecha_hora
            )
            estado.resumen_gps["texto_ultima_ubicacion"] = (
                fecha_ultima_transmision.strftime("%d-%m-%Y %H:%M")
            )

            minutos_desde_ultima = max(
                0,
                (
                    obtener_ahora_referencia() - fecha_ultima_transmision
                ).total_seconds() / 60,
            )

            if minutos_desde_ultima < 1:
                estado.resumen_gps["texto_tiempo_desde_ultima"] = "Hace menos de 1 min"
            elif minutos_desde_ultima < 60:
                estado.resumen_gps["texto_tiempo_desde_ultima"] = (
                    f"Hace {int(minutos_desde_ultima)} min"
                )
            elif minutos_desde_ultima < 1440:
                estado.resumen_gps["texto_tiempo_desde_ultima"] = (
                    f"Hace {int(minutos_desde_ultima // 60)} h"
                )
            else:
                dias_desde_ultima = int(minutos_desde_ultima // 1440)
                sufijo_dia = "día" if dias_desde_ultima == 1 else "días"
                estado.resumen_gps["texto_tiempo_desde_ultima"] = (
                    f"Hace {dias_desde_ultima} {sufijo_dia}"
                )

            if minutos_desde_ultima <= 60:
                estado.resumen_gps["clase_ultima_ubicacion"] = "gps-estado-ok"
            elif minutos_desde_ultima <= 180:
                estado.resumen_gps["clase_ultima_ubicacion"] = "gps-estado-advertencia"
            else:
                estado.resumen_gps["clase_ultima_ubicacion"] = "gps-estado-alerta"

        if ultimo_registro_reportado:
            referencia_actual = obtener_referencia_desde_cache(
                fecha_consulta=fecha_ultima_referencia,
                historial_amid=estado.historial_amid,
                vigente_amid=estado.vigente_amid,
            )

            ultima_reportada_es_cero = (
                ultima_ubicacion_reportada is not None
                and ultima_ubicacion_reportada.get("coordenada_cero") is True
            )

            if ultima_reportada_es_cero:
                distancia_actual = None
                dentro_radio_actual = None
            elif ultima_ubicacion_reportada:
                distancia_actual = calcular_distancia_metros(
                    ultima_ubicacion_reportada["latitud"],
                    ultima_ubicacion_reportada["longitud"],
                    referencia_actual["latitud"],
                    referencia_actual["longitud"],
                )

                dentro_radio_actual = (
                    distancia_actual <= referencia_actual["radio_metros"]
                    if distancia_actual is not None
                    else None
                )
            else:
                distancia_actual = None
                dentro_radio_actual = None

            estado.ubicacion_esperada = {
                "nombre": referencia_actual["nombre"],
                "latitud": referencia_actual["latitud"],
                "longitud": referencia_actual["longitud"],
                "radio_metros": referencia_actual["radio_metros"],
                "distancia_metros": round(distancia_actual, 2) if distancia_actual is not None else None,
                "dentro_radio": dentro_radio_actual,
                "operativa": referencia_actual["operativa"],
                "origen_ubicacion": referencia_actual["origen_ubicacion"],
                "version_zp": referencia_actual.get("version_zp"),
                "ultima_reportada_es_cero": ultima_reportada_es_cero,
            }

        if not estado.ubicaciones_gps and not estado.mensaje:
            estado.mensaje = (
                "No se encontraron coordenadas GPS para el AMID ingresado "
                "en el rango seleccionado."
            )

    except Exception as error:
        estado.mensaje = f"Error consultando ubicación esperada en Oracle: {error}"


def obtener_contexto_gps(request):
    amid = request.GET.get("amid", "").strip()
    horario_zp_solicitado = request.GET.get("horario_zp", "0") == "1"
    rango_manual = request.GET.get("rango_manual", "0")

    filtros_fecha = obtener_rango_fechas_gps(request)
    filtros_por_defecto = filtros_gps_son_por_defecto(
        request=request,
        filtros_fecha=filtros_fecha,
    )

    estado = SimpleNamespace(
        amid=amid,
        filtros_fecha=filtros_fecha,
        filtros_por_defecto=filtros_por_defecto,
        rango_manual=rango_manual,
        horario_zp_solicitado=horario_zp_solicitado,
        horario_zp=crear_configuracion_horario_zp(
            fecha_referencia=obtener_ahora_referencia()
        ),
        resumen_gps=crear_resumen_gps_rango(
            fecha_desde=filtros_fecha["fecha_desde"],
            fecha_hasta=filtros_fecha["fecha_hasta"],
            hora_desde=filtros_fecha["hora_desde"],
            hora_hasta=filtros_fecha["hora_hasta"],
        ),
        mensaje="",
        aviso_horario_zp="",
        usando_ultimo_dia_reportado=False,
        fecha_ultimo_dia_reportado=None,
        horario_zp_activo=False,
        ultimo_registro=None,
        latitud=None,
        longitud=None,
        ubicaciones_gps=[],
        historial_gps=[],
        ubicacion_esperada=None,
        historial_amid=[],
        vigente_amid=None,
    )

    if amid:
        _armar_resumen_amid_gps(estado)
        _armar_ubicacion_y_horario_gps(estado)
        _armar_detalle_periodo_gps(estado)

    return {
        "amid": amid,
        "fecha_desde": estado.filtros_fecha["fecha_desde_input"],
        "fecha_hasta": estado.filtros_fecha["fecha_hasta_input"],
        "hora_desde": estado.filtros_fecha["hora_desde"],
        "hora_hasta": estado.filtros_fecha["hora_hasta"],
        "bloques_horarios": estado.filtros_fecha["bloques_horarios"],
        "ultimo_registro": estado.ultimo_registro,
        "mensaje": estado.mensaje,
        "latitud": estado.latitud,
        "longitud": estado.longitud,
        "ubicaciones_gps": estado.ubicaciones_gps,
        "historial_gps": estado.historial_gps,
        "ubicacion_esperada": estado.ubicacion_esperada,
        "ubicacion_laboratorio": {
            "nombre": NOMBRE_LABORATORIO_ZP,
            "latitud": LATITUD_LABORATORIO_ZP,
            "longitud": LONGITUD_LABORATORIO_ZP,
            "radio_metros": RADIO_LABORATORIO_ZP,
        },
        "resumen_gps": estado.resumen_gps,
        "horario_zp_solicitado": estado.horario_zp_solicitado,
        "horario_zp_activo": estado.horario_zp_activo,
        "horario_zp": estado.horario_zp,
        "aviso_horario_zp": estado.aviso_horario_zp,
        "usando_ultimo_dia_reportado": estado.usando_ultimo_dia_reportado,
        "fecha_ultimo_dia_reportado": estado.fecha_ultimo_dia_reportado,
        "rango_manual": estado.rango_manual,
    }
