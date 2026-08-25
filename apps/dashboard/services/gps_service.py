from datetime import datetime, time, timedelta
from types import SimpleNamespace
import math

from django.utils import timezone

from apps.dashboard.services.horarios_zp_service import (
    crear_configuracion_horario_zp,
    filtrar_registros_por_horario_zp,
)
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
    Obtiene los bloques creados en Oracle dentro del rango solicitado.

    FECHA_REGISTRO representa la hora del bloque. FECHA_HORA es la hora
    reportada por el validador: si se repite respecto del bloque anterior,
    el equipo no transmitió un GPS nuevo y las coordenadas se normalizan a NULL.
    """

    query_anterior = """
        SELECT FECHA_HORA
        FROM (
            SELECT FECHA_HORA
            FROM USR_LAB.VW_ESTATUS_ZP_DJANGO
            WHERE AMID = :amid
              AND FECHA_REGISTRO < TO_DATE(:fecha_inicio, 'YYYY-MM-DD HH24:MI:SS')
            ORDER BY FECHA_REGISTRO DESC, ID DESC
        )
        WHERE ROWNUM = 1
    """

    query = """
        SELECT
            ID,
            AMID,
            FEC_DESCARGA,
            FEC_ESTADO,
            FECHA_HORA,
            FECHA_REGISTRO,
            LATITUD,
            LONGITUD,
            PORCENTAJE_BATERIA,
            IS_CONTIENE_GPS,
            IS_ERROR_OBTENER_GPS
        FROM USR_LAB.VW_ESTATUS_ZP_DJANGO
        WHERE AMID = :amid
          AND FECHA_REGISTRO >= TO_DATE(:fecha_inicio, 'YYYY-MM-DD HH24:MI:SS')
          AND FECHA_REGISTRO < TO_DATE(:fecha_fin, 'YYYY-MM-DD HH24:MI:SS')
        ORDER BY FECHA_REGISTRO, ID
    """

    parametros = {
        "amid": int(amid),
        "fecha_inicio": fecha_a_texto_oracle(fecha_inicio),
        "fecha_fin": fecha_a_texto_oracle(fecha_fin),
    }
    registros = []

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                query_anterior,
                {
                    "amid": parametros["amid"],
                    "fecha_inicio": parametros["fecha_inicio"],
                },
            )
            fila_anterior = cursor.fetchone()
            fecha_hora_anterior = normalizar_fecha_para_comparar(
                fila_anterior[0] if fila_anterior else None
            )

            cursor.execute(query, parametros)
            columnas = [col[0].lower() for col in cursor.description]

            for fila in cursor.fetchall():
                datos = dict(zip(columnas, fila))
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

    if registro.latitud is None or registro.longitud is None:
        return False

    try:
        latitud = float(registro.latitud)
        longitud = float(registro.longitud)
    except (ValueError, TypeError):
        return False

    return latitud == 0 and longitud == 0


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

    bloques_validos = generar_bloques_horarios()

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

    query = """
        SELECT *
        FROM (
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
              AND FECHA_HORA IS NOT NULL
              AND LATITUD IS NOT NULL
              AND LONGITUD IS NOT NULL
              AND NOT (LATITUD = 0 AND LONGITUD = 0)
            ORDER BY FECHA_HORA DESC
        )
        WHERE ROWNUM = 1
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, {"amid": int(amid)})

            fila = cursor.fetchone()

            if not fila:
                return None

            columnas = [col[0].lower() for col in cursor.description]
            datos = dict(zip(columnas, fila))

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
            HORARIO,
            HORARIO_LABORAL_PM,
            HORARIO_SABADO,
            HORARIO_DOMINGO,
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

        "registros_totales_periodo": 0,
        "registros_gps_reportados_periodo": 0,
        "registros_gps_validos_periodo": 0,
        "registros_sin_transmision_periodo": 0,
        "registros_gps_cero_periodo": 0,

        "porcentaje_cumplimiento_periodo": None,
        "clase_cumplimiento_periodo": "",

        "texto_periodo": textos_periodo["texto_periodo"],
        "texto_fechas_periodo": textos_periodo["texto_periodo"],
        "texto_horario_periodo": "",
        "texto_cumplimiento": textos_periodo["texto_cumplimiento"],
        "texto_dentro": textos_periodo["texto_dentro"],
        "texto_fuera": textos_periodo["texto_fuera"],

        "clase_ultima_ubicacion": "",
        "texto_ultima_ubicacion": "-",
        "texto_tiempo_desde_ultima": "",
    }


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
        # coordenadas válidas + coordenadas 0,0.
        # GPS 0,0 cuenta como fuera del radio.
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


def obtener_contexto_gps(request):
    amid = request.GET.get("amid", "").strip()
    horario_zp_solicitado = request.GET.get("horario_zp", "0") == "1"
    rango_manual = request.GET.get("rango_manual", "0")

    filtros_fecha = obtener_rango_fechas_gps(request)
    filtros_por_defecto = filtros_gps_son_por_defecto(
        request=request,
        filtros_fecha=filtros_fecha,
    )

    ultimo_registro = None
    mensaje = ""
    latitud = None
    longitud = None
    ubicaciones_gps = []
    historial_gps = []
    ubicacion_esperada = None
    usando_ultimo_dia_reportado = False
    fecha_ultimo_dia_reportado = None
    historial_amid = []
    vigente_amid = None
    horario_zp_activo = False
    horario_zp = crear_configuracion_horario_zp(
        fecha_referencia=obtener_ahora_referencia()
    )
    aviso_horario_zp = ""

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

            registros_reportados_inicial = [
                registro for registro in registros_periodo_base
                if gps_tiene_coordenadas(registro)
            ]

            # Fallback:
            # Solo buscamos el último día si NO hubo GPS reportado hoy.
            # Si hubo 0,0 hoy, se muestra hoy y se cuenta como fuera.
            if filtros_por_defecto and not registros_reportados_inicial:
                ultimo_gps_valido = obtener_ultimo_registro_gps_valido_oracle(amid)

                if ultimo_gps_valido and ultimo_gps_valido.fecha_hora:
                    fecha_ultimo_dia_reportado = ultimo_gps_valido.fecha_hora.date()
                    filtros_fecha = construir_filtros_gps_para_dia(
                        fecha_ultimo_dia_reportado
                    )

                    registros_periodo_base = obtener_registros_gps_oracle(
                        amid=amid,
                        fecha_inicio=filtros_fecha["fecha_inicio"],
                        fecha_fin=filtros_fecha["fecha_fin"],
                    )

                    usando_ultimo_dia_reportado = True
                    rango_manual = "0"

                    resumen_gps = crear_resumen_gps_rango(
                        fecha_desde=filtros_fecha["fecha_desde"],
                        fecha_hasta=filtros_fecha["fecha_hasta"],
                        hora_desde=filtros_fecha["hora_desde"],
                        hora_hasta=filtros_fecha["hora_hasta"],
                    )

                    mensaje = (
                        "El AMID no envió coordenadas GPS hoy. "
                        "Se muestran las últimas coordenadas válidas disponibles "
                        f"del {fecha_ultimo_dia_reportado.strftime('%d-%m-%Y')}."
                    )

        except ValueError:
            mensaje = "El AMID ingresado no es válido."
            registros_periodo_base = []
        except Exception as error:
            mensaje = f"Error consultando datos GPS en Oracle: {error}"
            registros_periodo_base = []

        try:
            with obtener_conexion_oracle() as conexion:
                with conexion.cursor() as cursor:
                    historial_amid = obtener_historial_ubicacion_amid(cursor, amid)
                    vigente_amid = obtener_ubicacion_vigente_amid(cursor, amid)

            horario_zp = crear_configuracion_horario_zp(
                datos=vigente_amid,
                fecha_referencia=obtener_ahora_referencia(),
            )
        except Exception as error:
            aviso_horario_zp = (
                "No fue posible consultar el horario vigente; "
                "los registros se mantienen sin filtro."
            )
            if not mensaje:
                mensaje = f"Error consultando ubicación esperada en Oracle: {error}"

        if horario_zp_solicitado and not horario_zp["tiene_horario_hoy"]:
            horario_zp_solicitado = False

        if horario_zp_solicitado and horario_zp["tiene_horario_hoy"]:
            registros_periodo_base, horario_zp_activo = (
                filtrar_registros_por_horario_zp(
                    registros=registros_periodo_base,
                    configuracion=horario_zp,
                    atributo_fecha="fecha_registro",
                )
            )

        resumen_gps["registros_totales_periodo"] = len(registros_periodo_base)

        resumen_gps["errores_gps_periodo"] = sum(
            1 for registro in registros_periodo_base
            if es_error_gps(registro)
        )

        resumen_gps["clase_errores_gps_periodo"] = obtener_clase_errores_gps(
            resumen_gps["errores_gps_periodo"]
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

        resumen_gps["registros_gps_reportados_periodo"] = len(registros_reportados)
        resumen_gps["registros_gps_validos_periodo"] = len(registros_validos)
        resumen_gps["registros_sin_transmision_periodo"] = len(
            registros_sin_transmision
        )
        resumen_gps["registros_gps_cero_periodo"] = len(registros_cero)

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
                    historial_amid=historial_amid,
                    vigente_amid=vigente_amid,
                )

                coordenada_cero = lat == 0 and lon == 0

                if coordenada_cero:
                    distancia = None
                    dentro_radio = False

                    # Regla operacional:
                    # 0,0 cuenta como fuera del radio.
                    resumen_gps["registros_periodo"] += 1
                    resumen_gps["registros_fuera_periodo"] += 1
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

                        resumen_gps["registros_periodo"] += 1

                        if dentro_radio:
                            resumen_gps["registros_dentro_periodo"] += 1
                        else:
                            resumen_gps["registros_fuera_periodo"] += 1

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
                    "indice_mapa": len(ubicaciones_gps),
                }

                ubicaciones_gps.append(ubicacion_mapa)
                ubicaciones_mapa_por_id[str(registro.id)] = ubicacion_mapa

                ultima_ubicacion_reportada = ubicacion_mapa
                ultimo_registro_reportado = registro

                if not coordenada_cero:
                    ultima_ubicacion_valida = ubicacion_mapa
                    ultimo_registro_valido = registro

            # El historial representa bloques, no sólo puntos del mapa.
            # FECHA_REGISTRO identifica el bloque; una FECHA_HORA repetida indica
            # que el validador no transmitió coordenadas nuevas en ese bloque.
            for registro in registros_periodo_base:
                ubicacion_transmitida = ubicaciones_mapa_por_id.get(str(registro.id))

                if ubicacion_transmitida is not None:
                    historial_gps.append(ubicacion_transmitida)
                    continue

                referencia_esperada = obtener_referencia_desde_cache(
                    fecha_consulta=registro.fecha_registro or registro.fecha_hora,
                    historial_amid=historial_amid,
                    vigente_amid=vigente_amid,
                )

                historial_gps.append({
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

            if resumen_gps["registros_periodo"] > 0:
                resumen_gps["porcentaje_cumplimiento_periodo"] = round(
                    resumen_gps["registros_dentro_periodo"] * 100 / resumen_gps["registros_periodo"],
                    1
                )

            resumen_gps["clase_cumplimiento_periodo"] = obtener_clase_cumplimiento(
                resumen_gps["porcentaje_cumplimiento_periodo"]
            )

            # Para centrar el mapa usamos la última coordenada válida.
            # Si solo hay 0,0, no centramos en 0,0.
            if ultima_ubicacion_valida:
                latitud = ultima_ubicacion_valida["latitud"]
                longitud = ultima_ubicacion_valida["longitud"]

            # Para estado y última ubicación usamos la última coordenada reportada.
            if ultimo_registro_reportado:
                ultimo_registro = ultimo_registro_reportado
                fecha_ultima_referencia = (
                    ultimo_registro_reportado.fecha_registro
                    or ultimo_registro_reportado.fecha_hora
                )
            else:
                fecha_ultima_referencia = None

            if ultimo_registro and (
                ultimo_registro.fecha_registro or ultimo_registro.fecha_hora
            ):
                fecha_ultima_transmision = (
                    ultimo_registro.fecha_registro or ultimo_registro.fecha_hora
                )
                resumen_gps["texto_ultima_ubicacion"] = (
                    fecha_ultima_transmision.strftime("%d-%m-%Y %H:%M")
                )

                minutos_desde_ultima = max(
                    0,
                    (
                        obtener_ahora_referencia() - fecha_ultima_transmision
                    ).total_seconds() / 60,
                )

                if minutos_desde_ultima < 1:
                    resumen_gps["texto_tiempo_desde_ultima"] = "Hace menos de 1 min"
                elif minutos_desde_ultima < 60:
                    resumen_gps["texto_tiempo_desde_ultima"] = (
                        f"Hace {int(minutos_desde_ultima)} min"
                    )
                elif minutos_desde_ultima < 1440:
                    resumen_gps["texto_tiempo_desde_ultima"] = (
                        f"Hace {int(minutos_desde_ultima // 60)} h"
                    )
                else:
                    dias_desde_ultima = int(minutos_desde_ultima // 1440)
                    sufijo_dia = "día" if dias_desde_ultima == 1 else "días"
                    resumen_gps["texto_tiempo_desde_ultima"] = (
                        f"Hace {dias_desde_ultima} {sufijo_dia}"
                    )

                if minutos_desde_ultima <= 60:
                    resumen_gps["clase_ultima_ubicacion"] = "gps-estado-ok"
                elif minutos_desde_ultima <= 180:
                    resumen_gps["clase_ultima_ubicacion"] = "gps-estado-advertencia"
                else:
                    resumen_gps["clase_ultima_ubicacion"] = "gps-estado-alerta"

            if ultimo_registro_reportado:
                referencia_actual = obtener_referencia_desde_cache(
                    fecha_consulta=fecha_ultima_referencia,
                    historial_amid=historial_amid,
                    vigente_amid=vigente_amid,
                )

                ultima_reportada_es_cero = (
                    ultima_ubicacion_reportada is not None
                    and ultima_ubicacion_reportada.get("coordenada_cero") is True
                )

                if ultima_reportada_es_cero:
                    distancia_actual = None
                    dentro_radio_actual = False
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

                ubicacion_esperada = {
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

            if not ubicaciones_gps and not mensaje:
                mensaje = (
                    "No se encontraron coordenadas GPS para el AMID ingresado "
                    "en el rango seleccionado."
                )

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
        "historial_gps": historial_gps,
        "ubicacion_esperada": ubicacion_esperada,
        "ubicacion_laboratorio": ubicacion_laboratorio,
        "resumen_gps": resumen_gps,

        "horario_zp_solicitado": horario_zp_solicitado,
        "horario_zp_activo": horario_zp_activo,
        "horario_zp": horario_zp,
        "aviso_horario_zp": aviso_horario_zp,

        "usando_ultimo_dia_reportado": usando_ultimo_dia_reportado,
        "fecha_ultimo_dia_reportado": fecha_ultimo_dia_reportado,
        "rango_manual": rango_manual,
    }