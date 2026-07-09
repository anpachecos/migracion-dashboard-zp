from datetime import datetime, time, timedelta
from types import SimpleNamespace
import math

from django.utils import timezone

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


LATITUD_LABORATORIO_ZP = -33.437191
LONGITUD_LABORATORIO_ZP = -70.656102
RADIO_LABORATORIO_ZP = 150
NOMBRE_LABORATORIO_ZP = "Laboratorio Zonas Pagas"


def obtener_ahora_referencia():
    """
    Devuelve la hora actual local como datetime naive.
    Se usa naive para comparar con fechas que vienen desde Oracle.
    """

    ahora = timezone.localtime(timezone.now())

    if timezone.is_aware(ahora):
        return timezone.make_naive(ahora)

    return ahora


def normalizar_fecha_para_comparar(fecha):
    """
    Deja las fechas sin tzinfo para evitar desfases.
    Oracle ya trae las fechas en la hora correcta.
    """

    if not fecha:
        return None

    if timezone.is_aware(fecha):
        return timezone.make_naive(fecha)

    return fecha


def fecha_a_texto_oracle(fecha):
    fecha = normalizar_fecha_para_comparar(fecha)

    if not fecha:
        return None

    return fecha.strftime("%Y-%m-%d %H:%M:%S")


def normalizar_booleano_oracle(valor):
    if valor is None:
        return False

    if isinstance(valor, bool):
        return valor

    if isinstance(valor, (int, float)):
        return int(valor) == 1

    return str(valor).strip().upper() in ["TRUE", "1", "SI", "SÍ", "Y"]


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
        }
    except (ValueError, TypeError):
        return None

def generar_bloques_horarios():
    bloques = []

    for hora in range(24):
        for minuto in [0, 30]:
            bloques.append(f"{hora:02d}:{minuto:02d}")

    return bloques


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

    bloques_validos = generar_bloques_horarios()

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

def obtener_rango_fechas_periodo(dias):
    hoy = obtener_ahora_referencia().date()
    fecha_inicio = hoy - timedelta(days=dias - 1)

    inicio = datetime.combine(fecha_inicio, time.min)
    fin = datetime.combine(hoy + timedelta(days=1), time.min)

    return inicio, fin

def obtener_registros_gps_oracle(amid, fecha_inicio, fecha_fin):
    """
    Obtiene registros GPS directamente desde Oracle usando rango exacto
    de fecha/hora.
    """

    query = """
        SELECT
            ID,
            AMID,
            FEC_DESCARGA,
            FEC_ESTADO,
            FECHA_HORA,
            LATITUD,
            LONGITUD,
            PORCENTAJE_BATERIA,
            IS_CONTIENE_GPS,
            IS_ERROR_OBTENER_GPS
        FROM USR_LAB.VW_ESTATUS_ZP_DJANGO
        WHERE AMID = :amid
          AND FECHA_HORA >= TO_DATE(:fecha_inicio, 'YYYY-MM-DD HH24:MI:SS')
          AND FECHA_HORA < TO_DATE(:fecha_fin, 'YYYY-MM-DD HH24:MI:SS')
        ORDER BY FECHA_HORA
    """

    registros = []

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "amid": int(amid),
                    "fecha_inicio": fecha_a_texto_oracle(fecha_inicio),
                    "fecha_fin": fecha_a_texto_oracle(fecha_fin),
                }
            )

            columnas = [col[0].lower() for col in cursor.description]

            for fila in cursor.fetchall():
                datos = dict(zip(columnas, fila))

                registros.append(
                    SimpleNamespace(
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
                )

    return registros

def obtener_historial_ubicacion_amid(cursor, amid):
    """
    Trae una sola vez todo el historial del AMID.
    Luego se resuelve en Python qué ubicación correspondía a cada fecha.
    """

    query = """
        SELECT
            AMID,
            NOMBRE,
            LATITUD_ESPERADA,
            LONGITUD_ESPERADA,
            RADIO_METROS,
            OPERATIVA,
            ORIGEN_UBICACION,
            VERSION_ZP,
            ARCHIVO_ORIGEN,
            FECHA_INICIO_VIGENCIA,
            FECHA_FIN_VIGENCIA
        FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA
        WHERE AMID = :amid
        ORDER BY FECHA_INICIO_VIGENCIA
    """

    cursor.execute(query, {"amid": str(amid).strip()})

    columnas = [col[0] for col in cursor.description]
    historial = []

    for fila in cursor.fetchall():
        datos = dict(zip(columnas, fila))
        datos["FECHA_INICIO_VIGENCIA"] = normalizar_fecha_para_comparar(
            datos.get("FECHA_INICIO_VIGENCIA")
        )
        datos["FECHA_FIN_VIGENCIA"] = normalizar_fecha_para_comparar(
            datos.get("FECHA_FIN_VIGENCIA")
        )
        historial.append(datos)

    return historial


def obtener_ubicacion_vigente_amid(cursor, amid):
    """
    Trae la ubicación vigente del AMID desde Oracle.
    """

    query = """
        SELECT
            AMID,
            NOMBRE,
            LATITUD_ESPERADA,
            LONGITUD_ESPERADA,
            RADIO_METROS,
            OPERATIVA,
            VERSION_ZP,
            ARCHIVO_ORIGEN,
            FECHA_CARGA
        FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
        WHERE AMID = :amid
    """

    cursor.execute(query, {"amid": str(amid).strip()})

    fila = cursor.fetchone()

    if not fila:
        return None

    columnas = [col[0] for col in cursor.description]
    datos = dict(zip(columnas, fila))
    datos["ORIGEN_UBICACION"] = "vigente"

    return datos


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


def obtener_referencia_esperada(amid, fecha_consulta=None):
    """
    Función compatible para otros módulos.
    Si otro servicio la llama directamente, consulta Oracle.
    En el panel GPS optimizado usamos obtener_referencia_desde_cache().
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            historial = obtener_historial_ubicacion_amid(cursor, amid)
            vigente = obtener_ubicacion_vigente_amid(cursor, amid)

    return obtener_referencia_desde_cache(
        fecha_consulta=fecha_consulta,
        historial_amid=historial,
        vigente_amid=vigente,
    )


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

def crear_resumen_gps_rango(fecha_desde, fecha_hasta, hora_desde, hora_hasta):
    if fecha_desde == fecha_hasta:
        texto_periodo = f"{fecha_desde.strftime('%d-%m-%Y')} {hora_desde} a {hora_hasta}"
    else:
        texto_periodo = (
            f"{fecha_desde.strftime('%d-%m-%Y')} {hora_desde} "
            f"a {fecha_hasta.strftime('%d-%m-%Y')} {hora_hasta}"
        )

    return {
        "errores_gps_periodo": 0,
        "clase_errores_gps_periodo": "gps-estado-ok",

        "registros_periodo": 0,
        "registros_dentro_periodo": 0,
        "registros_fuera_periodo": 0,
        "porcentaje_cumplimiento_periodo": None,
        "clase_cumplimiento_periodo": "",

        "texto_periodo": texto_periodo,
        "texto_cumplimiento": "Cumplimiento período",
        "texto_dentro": "Dentro período",
        "texto_fuera": "Fuera período",

        "clase_ultima_ubicacion": "",
        "texto_ultima_ubicacion": "-",
    }

def obtener_contexto_gps(request):
    amid = request.GET.get("amid", "").strip()
    filtros_fecha = obtener_rango_fechas_gps(request)

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

    resumen_gps = crear_resumen_gps_rango(
        fecha_desde=filtros_fecha["fecha_desde"],
        fecha_hasta=filtros_fecha["fecha_hasta"],
        hora_desde=filtros_fecha["hora_desde"],
        hora_hasta=filtros_fecha["hora_hasta"],
    )

    if amid:
        try:
            registros_periodo_base = obtener_registros_gps_oracle(
                amid=amid,
                fecha_inicio=filtros_fecha["fecha_inicio"],
                fecha_fin=filtros_fecha["fecha_fin"],
            )
        except ValueError:
            mensaje = "El AMID ingresado no es válido."
            registros_periodo_base = []
        except Exception as error:
            mensaje = f"Error consultando datos GPS en Oracle: {error}"
            registros_periodo_base = []

        resumen_gps["errores_gps_periodo"] = sum(
            1 for registro in registros_periodo_base
            if es_error_gps(registro)
        )

        resumen_gps["clase_errores_gps_periodo"] = obtener_clase_errores_gps(
            resumen_gps["errores_gps_periodo"]
        )

        registros = [
            registro for registro in registros_periodo_base
            if registro.latitud is not None and registro.longitud is not None
        ]

        try:
            with obtener_conexion_oracle() as conexion:
                with conexion.cursor() as cursor:
                    historial_amid = obtener_historial_ubicacion_amid(cursor, amid)
                    vigente_amid = obtener_ubicacion_vigente_amid(cursor, amid)

            for registro in registros:
                try:
                    lat = float(registro.latitud)
                    lon = float(registro.longitud)
                except (ValueError, TypeError):
                    continue

                referencia_esperada = obtener_referencia_desde_cache(
                    fecha_consulta=registro.fecha_hora,
                    historial_amid=historial_amid,
                    vigente_amid=vigente_amid,
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

                    resumen_gps["registros_periodo"] += 1

                    if dentro_radio:
                        resumen_gps["registros_dentro_periodo"] += 1
                    else:
                        resumen_gps["registros_fuera_periodo"] += 1

                ubicaciones_gps.append({
                    "latitud": lat,
                    "longitud": lon,
                    "fecha_hora": registro.fecha_hora.strftime("%d-%m-%Y %H:%M") if registro.fecha_hora else "",
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
                ultimo_registro = registros[-1] if registros else None

                fecha_ultima_referencia = None

                if ultimo_registro and ultimo_registro.fecha_hora:
                    fecha_ultima_referencia = ultimo_registro.fecha_hora

                    resumen_gps["texto_ultima_ubicacion"] = (
                        ultimo_registro.fecha_hora.strftime("%d-%m-%Y %H:%M")
                    )

                    minutos_desde_ultima = (
                        obtener_ahora_referencia() - ultimo_registro.fecha_hora
                    ).total_seconds() / 60

                    if minutos_desde_ultima <= 60:
                        resumen_gps["clase_ultima_ubicacion"] = "gps-estado-ok"
                    elif minutos_desde_ultima <= 180:
                        resumen_gps["clase_ultima_ubicacion"] = "gps-estado-advertencia"
                    else:
                        resumen_gps["clase_ultima_ubicacion"] = "gps-estado-alerta"

                referencia_actual = obtener_referencia_desde_cache(
                    fecha_consulta=fecha_ultima_referencia,
                    historial_amid=historial_amid,
                    vigente_amid=vigente_amid,
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

            elif not mensaje:
                mensaje = "No se encontraron coordenadas GPS para el AMID ingresado en el rango seleccionado."

        except Exception as error:
            mensaje = f"Error consultando ubicación esperada en Oracle: {error}"

    return {
        "amid": amid,

        "fecha_desde": filtros_fecha["fecha_desde_input"],
        "fecha_hasta": filtros_fecha["fecha_hasta_input"],
        "hora_desde": filtros_fecha["hora_desde"],
        "hora_hasta": filtros_fecha["hora_hasta"],
        "bloques_horarios": filtros_fecha["bloques_horarios"],

        "ultimo_registro": ultimo_registro,
        "mensaje": mensaje,
        "latitud": latitud,
        "longitud": longitud,
        "ubicaciones_gps": ubicaciones_gps,
        "ubicacion_esperada": ubicacion_esperada,
        "ubicacion_laboratorio": ubicacion_laboratorio,
        "resumen_gps": resumen_gps,
    }