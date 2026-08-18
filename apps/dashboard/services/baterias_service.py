from datetime import datetime, timedelta
from types import SimpleNamespace

from django.core.cache import cache
from django.utils import timezone

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


CACHE_KEY_REGLAS_CAIDAS_BATERIA = "dashboard:reglas-caidas-bateria:v1"
CACHE_TIMEOUT_REGLAS_CAIDAS_BATERIA = 300
CLAVES_REGLAS_CAIDAS_BATERIA = (
    "BAT_CAIDA_MIN_DETECTAR",
    "BAT_CAIDA_MAX_HORAS",
)


"""
REGLAS DE NEGOCIO ACTUALES

Oracle:
- USR_LAB.BATERIA_BLOQUE_30MIN ya tiene una fila por AMID + bloque de 30 minutos.
- Si no hubo transmisión cercana al bloque:
    PORCENTAJE_BATERIA = NULL
    TIENE_DATO = 0
- Si hubo dato real con batería 0:
    PORCENTAJE_BATERIA = 0
    TIENE_DATO = 1
- La tabla se actualiza con job Oracle cada 30 minutos.

Python:
- Lee la tabla de bloques ya preparada.
- No vuelve a calcular el registro más cercano.
- Arma la estructura para HTML y gráficos.
- El último registro / tarjetas salen desde VW_ESTATUS_ZP_DJANGO.
- El nivel de alerta se lee desde USR_LAB.ALERTA_VALIDADOR_RESUMEN.
- El detalle de cada caída se reconstruye desde los bloques usando los umbrales
  activos de USR_LAB.ALERTA_REGLA_PARAM.
"""


def obtener_ahora_referencia():
    """
    Retorna la fecha/hora actual sin tzinfo para comparar con fechas Oracle.
    Oracle ya entrega las fechas en la hora correcta, por eso evitamos conversiones
    que puedan generar desfase.
    """
    ahora = timezone.localtime(timezone.now())

    if timezone.is_aware(ahora):
        return timezone.make_naive(ahora)

    return ahora


def normalizar_fecha_para_comparar(fecha):
    """
    Evita errores al comparar/restar fechas aware vs naive.
    No cambia la hora funcional, solo quita tzinfo si existe.
    """
    if not fecha:
        return None

    if timezone.is_aware(fecha):
        return timezone.make_naive(fecha)

    return fecha


def obtener_fecha(valor):
    """
    Devuelve solo la fecha, sin aplicar timezone.localtime().
    """
    if not valor:
        return None

    valor = normalizar_fecha_para_comparar(valor)
    return valor.date()


def normalizar_booleano_oracle(valor):
    """
    Normaliza valores booleanos que pueden venir desde Oracle como:
    1/0, true/false, TRUE/FALSE, Sí/No, etc.
    """
    if valor is None:
        return None

    if valor in [True, False]:
        return valor

    texto = str(valor).strip().lower()

    if texto in ["true", "1", "si", "sí", "s", "yes", "y"]:
        return True

    if texto in ["false", "0", "no", "n"]:
        return False

    return None


def convertir_numero(valor):
    """
    Convierte valores numéricos Oracle/Python a float.
    """
    if valor is None or valor == "":
        return None

    try:
        return float(valor)
    except (ValueError, TypeError):
        return None


def convertir_entero(valor, defecto=0):
    """
    Convierte valores numéricos Oracle/Python a int.
    """
    numero = convertir_numero(valor)

    if numero is None:
        return defecto

    return int(numero)


def formatear_bateria_entera(valor):
    """
    Normaliza batería para mostrarla sin decimales.

    Reglas:
    - None o vacío quedan como "" para que el HTML muestre "-".
    - 80.0 queda como 80.
    - 0 queda como 0, porque sí es un dato real.
    """
    if valor is None or valor == "":
        return ""

    try:
        numero = float(valor)
    except (ValueError, TypeError):
        return ""

    return int(round(numero))


def obtener_rango_fechas_panel(cantidad_dias):
    """
    Retorna rango calendario para consultar bloques.

    Ejemplo:
    cantidad_dias = 1
    -> hoy 00:00 hasta mañana 00:00

    cantidad_dias = 14
    -> hoy - 13 días a las 00:00 hasta mañana 00:00
    """
    hoy = obtener_ahora_referencia().date()

    fecha_inicio = datetime.combine(
        hoy - timedelta(days=cantidad_dias - 1),
        datetime.min.time(),
    )

    fecha_fin = datetime.combine(
        hoy + timedelta(days=1),
        datetime.min.time(),
    )

    return fecha_inicio, fecha_fin


def obtener_ultimo_registro_bateria_oracle(amid):
    """
    Obtiene el último registro real del AMID desde la vista original.

    Esta consulta alimenta las tarjetas:
    - Batería actual
    - Última descarga
    - Último estatus
    - Identificación
    - Sensor batería
    """
    query = """
        SELECT *
        FROM (
            SELECT
                ID,
                AMID,
                FEC_DESCARGA,
                FEC_ESTADO,
                BUSID,
                OP,
                VERSION,
                PATENTE,
                TD01,
                TD04,
                FECHA_HORA,
                PORCENTAJE_BATERIA,
                IS_CONTIENE_BATERIA,
                IS_ERROR_OBTENER_BATERIA
            FROM USR_LAB.VW_ESTATUS_ZP_DJANGO
            WHERE AMID = :amid
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
        fec_descarga=normalizar_fecha_para_comparar(
            datos.get("fec_descarga")
        ),
        fec_estado=normalizar_fecha_para_comparar(
            datos.get("fec_estado")
        ),
        fecha_hora=normalizar_fecha_para_comparar(
            datos.get("fecha_hora")
        ),
        busid=datos.get("busid"),
        op=datos.get("op"),
        version=datos.get("version"),
        patente=datos.get("patente"),
        td01=datos.get("td01"),
        td04=datos.get("td04"),
        porcentaje_bateria=formatear_bateria_entera(
            datos.get("porcentaje_bateria")
        ),
        is_contiene_bateria=normalizar_booleano_oracle(
            datos.get("is_contiene_bateria")
        ),
        is_error_obtener_bateria=normalizar_booleano_oracle(
            datos.get("is_error_obtener_bateria")
        ),
    )


def obtener_bloques_bateria_oracle(amid, fecha_inicio, fecha_fin):
    """
    Obtiene los bloques de batería ya preparados en Oracle.

    Esta consulta alimenta:
    - tabla por media hora
    - gráfico diario
    - gráfico período
    """
    fecha_inicio = normalizar_fecha_para_comparar(fecha_inicio)
    fecha_fin = normalizar_fecha_para_comparar(fecha_fin)

    query = """
        SELECT
            AMID,
            FECHA_HORA_BLOQUE,
            FECHA_BLOQUE,
            HORA_BLOQUE,
            PORCENTAJE_BATERIA,
            FECHA_HORA_ORIGINAL,
            ID_ORACLE,
            DIFERENCIA_MINUTOS,
            TIENE_DATO
        FROM USR_LAB.BATERIA_BLOQUE_30MIN
        WHERE AMID = :amid
          AND FECHA_HORA_BLOQUE >= :fecha_inicio
          AND FECHA_HORA_BLOQUE < :fecha_fin
        ORDER BY FECHA_HORA_BLOQUE
    """

    bloques = []

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "amid": int(amid),
                    "fecha_inicio": fecha_inicio,
                    "fecha_fin": fecha_fin,
                },
            )

            columnas = [col[0].lower() for col in cursor.description]

            for fila in cursor.fetchall():
                datos = dict(zip(columnas, fila))

                fecha_hora_bloque = normalizar_fecha_para_comparar(
                    datos.get("fecha_hora_bloque")
                )

                fecha_hora_original = normalizar_fecha_para_comparar(
                    datos.get("fecha_hora_original")
                )

                bloques.append(
                    SimpleNamespace(
                        amid=datos.get("amid"),
                        fecha_hora=fecha_hora_bloque,
                        fecha_hora_bloque=fecha_hora_bloque,
                        fecha_bloque=normalizar_fecha_para_comparar(
                            datos.get("fecha_bloque")
                        ),
                        hora_bloque=datos.get("hora_bloque"),
                        porcentaje_bateria=formatear_bateria_entera(
                            datos.get("porcentaje_bateria")
                        ),
                        fecha_hora_original=fecha_hora_original,
                        id_oracle=datos.get("id_oracle"),
                        diferencia_minutos=datos.get("diferencia_minutos"),
                        tiene_dato=datos.get("tiene_dato") == 1,
                    )
                )

    return bloques


def obtener_reglas_caidas_bateria_oracle():
    """Obtiene desde Oracle las reglas activas necesarias para detectar caídas."""
    reglas_cache = cache.get(CACHE_KEY_REGLAS_CAIDAS_BATERIA)
    if reglas_cache is not None:
        return reglas_cache

    query = """
        SELECT CLAVE, VALOR_NUMERO
        FROM USR_LAB.ALERTA_REGLA_PARAM
        WHERE ACTIVO = 1
          AND CLAVE IN (:clave_minima, :clave_horas)
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "clave_minima": CLAVES_REGLAS_CAIDAS_BATERIA[0],
                    "clave_horas": CLAVES_REGLAS_CAIDAS_BATERIA[1],
                },
            )
            reglas = {
                str(clave).strip().upper(): convertir_numero(valor)
                for clave, valor in cursor.fetchall()
            }

    faltantes = [
        clave
        for clave in CLAVES_REGLAS_CAIDAS_BATERIA
        if reglas.get(clave) is None
    ]
    if faltantes:
        raise RuntimeError(
            "Faltan reglas activas para detectar caídas de batería: "
            + ", ".join(faltantes)
        )

    reglas_normalizadas = {
        "caida_minima": reglas["BAT_CAIDA_MIN_DETECTAR"],
        "max_horas": reglas["BAT_CAIDA_MAX_HORAS"],
    }
    cache.set(
        CACHE_KEY_REGLAS_CAIDAS_BATERIA,
        reglas_normalizadas,
        CACHE_TIMEOUT_REGLAS_CAIDAS_BATERIA,
    )
    return reglas_normalizadas


def formatear_duracion_caida(diferencia):
    """Convierte un timedelta a un texto breve para el detalle visual."""
    minutos = max(0, int(round(diferencia.total_seconds() / 60)))
    horas, minutos_restantes = divmod(minutos, 60)

    if horas and minutos_restantes:
        return f"{horas} h {minutos_restantes} min"
    if horas:
        return f"{horas} h"
    return f"{minutos_restantes} min"


def detectar_caidas_bateria_en_bloques(bloques, caida_minima, max_horas):
    """
    Reconstruye cada caída comparando bloques consecutivos con dato real.

    Los umbrales no están definidos en Django: se reciben desde
    ``ALERTA_REGLA_PARAM`` para conservar una sola fuente de reglas.
    """
    bloques_validos = sorted(
        (
            bloque
            for bloque in bloques
            if bloque.tiene_dato
            and bloque.fecha_hora is not None
            and convertir_numero(bloque.porcentaje_bateria) is not None
        ),
        key=lambda bloque: bloque.fecha_hora,
    )
    alertas = []

    for anterior, actual in zip(bloques_validos, bloques_validos[1:]):
        diferencia_tiempo = actual.fecha_hora - anterior.fecha_hora
        diferencia_horas = diferencia_tiempo.total_seconds() / 3600
        bateria_anterior = convertir_numero(anterior.porcentaje_bateria)
        bateria_actual = convertir_numero(actual.porcentaje_bateria)
        caida = bateria_anterior - bateria_actual

        if not (0 < diferencia_horas <= max_horas and caida >= caida_minima):
            continue

        duracion = formatear_duracion_caida(diferencia_tiempo)
        caida_formateada = formatear_bateria_entera(caida)
        alertas.append(
            {
                "fecha_anterior": anterior.fecha_hora,
                "fecha_hora": actual.fecha_hora,
                "bateria_anterior": formatear_bateria_entera(bateria_anterior),
                "bateria_actual": formatear_bateria_entera(bateria_actual),
                "caida": caida_formateada,
                "tiempo_transcurrido": duracion,
                "motivo": f"Caída de {caida_formateada} puntos en {duracion}",
            }
        )

    return list(reversed(alertas))


def obtener_detalle_caidas_bateria_oracle(amid, dias=14):
    """Obtiene bajo demanda todas las caídas de un AMID en los últimos días."""
    fecha_inicio, fecha_fin = obtener_rango_fechas_panel(dias)
    bloques = obtener_bloques_bateria_oracle(
        amid=amid,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )
    reglas = obtener_reglas_caidas_bateria_oracle()
    alertas = detectar_caidas_bateria_en_bloques(
        bloques,
        caida_minima=reglas["caida_minima"],
        max_horas=reglas["max_horas"],
    )
    return {
        "amid": int(amid),
        "dias": int(dias),
        "caida_minima": reglas["caida_minima"],
        "max_horas": reglas["max_horas"],
        "total": len(alertas),
        "alertas": alertas,
    }


def obtener_resumen_alerta_bateria_oracle(amid):
    """
    Obtiene el resumen oficial de alertas de batería desde Oracle.

    Esta función permite que el Panel Baterías use la misma fuente de alertas
    que el Panel Alertas.
    """
    query = """
        SELECT
            AMID,
            CAIDAS_HOY,
            CAIDAS_HIST,
            ULTIMA_FECHA_CAIDA,
            ULTIMA_CAIDA_DESDE,
            ULTIMA_CAIDA_HASTA,
            ULTIMA_CAIDA_DIF,
            CAIDA_MAX_HOY,
            CAIDA_MAX_HIST,
            BATERIA_CERO_HOY,
            BATERIA_CERO_HIST,
            ULTIMA_FECHA_BAT_CERO,
            ULT_BLOQUE_BAT_ES_CERO,
            BATERIA_ACTUAL,
            ULTIMA_FECHA_BATERIA,
            NIVEL_ALERTA_BATERIA,
            MOTIVO_ALERTA_BATERIA,
            FECHA_ACTUALIZACION
        FROM USR_LAB.ALERTA_VALIDADOR_RESUMEN
        WHERE AMID = :amid
    """

    try:
        with obtener_conexion_oracle() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(query, {"amid": int(amid)})
                fila = cursor.fetchone()

                if not fila:
                    return None

                columnas = [col[0].lower() for col in cursor.description]
                datos = dict(zip(columnas, fila))

    except Exception:
        return None

    caidas_hoy = convertir_entero(datos.get("caidas_hoy"))
    caidas_hist = convertir_entero(datos.get("caidas_hist"))

    return SimpleNamespace(
        amid=datos.get("amid"),
        caidas_hoy=caidas_hoy,
        caidas_hist=caidas_hist,
        total_caidas=caidas_hoy + caidas_hist,
        ultima_fecha_caida=normalizar_fecha_para_comparar(
            datos.get("ultima_fecha_caida")
        ),
        ultima_caida_desde=convertir_numero(
            datos.get("ultima_caida_desde")
        ),
        ultima_caida_hasta=convertir_numero(
            datos.get("ultima_caida_hasta")
        ),
        ultima_caida_dif=convertir_numero(
            datos.get("ultima_caida_dif")
        ),
        caida_max_hoy=convertir_numero(
            datos.get("caida_max_hoy")
        ),
        caida_max_hist=convertir_numero(
            datos.get("caida_max_hist")
        ),
        bateria_cero_hoy=convertir_entero(
            datos.get("bateria_cero_hoy")
        ),
        bateria_cero_hist=convertir_entero(
            datos.get("bateria_cero_hist")
        ),
        ultima_fecha_bat_cero=normalizar_fecha_para_comparar(
            datos.get("ultima_fecha_bat_cero")
        ),
        ult_bloque_bat_es_cero=datos.get("ult_bloque_bat_es_cero") == 1,
        bateria_actual=formatear_bateria_entera(
            datos.get("bateria_actual")
        ),
        ultima_fecha_bateria=normalizar_fecha_para_comparar(
            datos.get("ultima_fecha_bateria")
        ),
        nivel_alerta_bateria=datos.get("nivel_alerta_bateria") or "OK",
        motivo_alerta_bateria=datos.get("motivo_alerta_bateria"),
        fecha_actualizacion=normalizar_fecha_para_comparar(
            datos.get("fecha_actualizacion")
        ),
    )


def construir_alertas_periodo_desde_resumen(resumen_alerta):
    """
    Construye una lista compatible con el template actual usando el resumen Oracle.

    Nota:
    ALERTA_VALIDADOR_RESUMEN entrega resumen por AMID, no todos los eventos
    detalle. Por eso aquí se muestra la última caída conocida y el conteo oficial.
    """
    if not resumen_alerta:
        return []

    if resumen_alerta.total_caidas <= 0:
        return []

    if not resumen_alerta.ultima_fecha_caida:
        return []

    return [
        {
            "usa_resumen_oracle": True,
            "fecha_hora": resumen_alerta.ultima_fecha_caida,
            "fecha_anterior": resumen_alerta.ultima_fecha_caida,
            "bateria_anterior": formatear_bateria_entera(
                resumen_alerta.ultima_caida_desde
            ),
            "bateria_actual": formatear_bateria_entera(
                resumen_alerta.ultima_caida_hasta
            ),
            "caida": formatear_bateria_entera(
                resumen_alerta.ultima_caida_dif
            ),
            "tiempo_transcurrido": "según reglas Oracle",
            "motivo": resumen_alerta.motivo_alerta_bateria,
            "total_caidas_hoy": resumen_alerta.caidas_hoy,
            "total_caidas_hist": resumen_alerta.caidas_hist,
        }
    ]


def obtener_clase_tarjeta_bateria(valor):
    if valor is None or valor == "":
        return "tarjeta-neutra"

    try:
        valor = float(valor)
    except (ValueError, TypeError):
        return "tarjeta-neutra"

    if valor >= 80:
        return "tarjeta-ok"

    if valor >= 50:
        return "tarjeta-warning"

    if valor >= 20:
        return "tarjeta-warning"

    return "tarjeta-error"


def obtener_clase_alertas_bateria(resumen_alerta):
    """
    Define la clase visual de la tarjeta Alertas período usando el nivel Oracle.
    """
    if not resumen_alerta:
        return "tarjeta-neutra"

    nivel = resumen_alerta.nivel_alerta_bateria

    if nivel == "CRITICA":
        return "tarjeta-error"

    if nivel in ["ALTA", "ADVERTENCIA"]:
        return "tarjeta-warning"

    if resumen_alerta.total_caidas > 0:
        return "tarjeta-warning"

    return "tarjeta-ok"


def evaluar_fecha_descarga(fecha_descarga):
    if not fecha_descarga:
        return "Sin dato", "tarjeta-neutra"

    fecha = obtener_fecha(fecha_descarga)
    hoy = obtener_ahora_referencia().date()

    if fecha == hoy:
        return "Hoy", "tarjeta-ok"

    return "No descargó hoy", "tarjeta-error"


def evaluar_fecha_estatus(fecha_estado):
    if not fecha_estado:
        return "Sin dato", "tarjeta-neutra"

    fecha_estado = normalizar_fecha_para_comparar(fecha_estado)
    ahora = obtener_ahora_referencia()
    hoy = ahora.date()

    if fecha_estado.date() != hoy:
        return "Sin estatus hoy", "tarjeta-error"

    diferencia_horas = (ahora - fecha_estado).total_seconds() / 3600

    if diferencia_horas <= 1:
        return "Actualizado", "tarjeta-ok"

    return "Hace más de 1 hora", "tarjeta-warning"


def evaluar_chip_booleano(valor, texto_ok="Sí", texto_error="No"):
    valor = normalizar_booleano_oracle(valor)

    if valor is True:
        return texto_ok, "chip-ok"

    if valor is False:
        return texto_error, "chip-error"

    return "Sin dato", "chip-neutro"


def evaluar_error_bateria(valor):
    valor = normalizar_booleano_oracle(valor)

    if valor is True:
        return "Sí", "chip-error"

    if valor is False:
        return "No", "chip-ok"

    return "Sin dato", "chip-neutro"


def obtener_contexto_baterias(request):
    amid = request.GET.get("amid", "").strip()

    # El panel de baterías trabaja siempre con 14 días completos.
    # Se eliminan filtros manuales para simplificar el uso operativo.
    dias = 14
    hora_inicio = "00:00"
    hora_fin = "23:30"

    ultimo_registro = None
    bloques = []
    columnas_horas = generar_columnas_media_hora(hora_inicio, hora_fin)
    tabla_bateria = []
    datos_grafico_dia = []
    datos_grafico_periodo = []
    mensaje = ""

    horario_sugerido_aplicado = False

    clase_bateria_actual = "tarjeta-neutra"

    estado_descarga = "-"
    clase_descarga = "tarjeta-neutra"

    estado_estatus = "-"
    clase_estado = "tarjeta-neutra"

    texto_contiene_bateria = "Sin dato"
    clase_contiene_bateria = "chip-neutro"

    texto_error_bateria = "Sin dato"
    clase_error_bateria = "chip-neutro"

    resumen_alerta_bateria = None
    total_caidas_drasticas = 0
    clase_alertas_periodo = "tarjeta-neutra"
    alertas_periodo = []
    detalle_alertas_completo = False

    if amid:
        try:
            fecha_inicio_consulta, fecha_fin_consulta = obtener_rango_fechas_panel(
                dias
            )

            bloques = obtener_bloques_bateria_oracle(
                amid=amid,
                fecha_inicio=fecha_inicio_consulta,
                fecha_fin=fecha_fin_consulta,
            )

            ultimo_registro = obtener_ultimo_registro_bateria_oracle(
                amid=amid
            )

            resumen_alerta_bateria = obtener_resumen_alerta_bateria_oracle(
                amid=amid
            )

        except ValueError:
            bloques = []
            ultimo_registro = None
            resumen_alerta_bateria = None
            mensaje = "El AMID ingresado no es válido."

        except Exception as error:
            bloques = []
            ultimo_registro = None
            resumen_alerta_bateria = None
            mensaje = f"Error consultando datos de baterías en Oracle: {error}"

        if ultimo_registro:
            columnas_horas, tabla_bateria = construir_tabla_bateria(
                bloques=bloques,
                cantidad_dias=dias,
                hora_inicio=hora_inicio,
                hora_fin=hora_fin,
            )

            datos_grafico_periodo = construir_datos_grafico_periodo(
                tabla_bateria
            )

            datos_grafico_dia = construir_datos_grafico_dia(
                bloques
            )

            clase_bateria_actual = obtener_clase_tarjeta_bateria(
                ultimo_registro.porcentaje_bateria
            )

            estado_descarga, clase_descarga = evaluar_fecha_descarga(
                ultimo_registro.fec_descarga
            )

            estado_estatus, clase_estado = evaluar_fecha_estatus(
                ultimo_registro.fec_estado
            )

            texto_contiene_bateria, clase_contiene_bateria = evaluar_chip_booleano(
                ultimo_registro.is_contiene_bateria
            )

            texto_error_bateria, clase_error_bateria = evaluar_error_bateria(
                ultimo_registro.is_error_obtener_bateria
            )

            if resumen_alerta_bateria:
                clase_alertas_periodo = obtener_clase_alertas_bateria(
                    resumen_alerta_bateria
                )
                try:
                    reglas_caidas = obtener_reglas_caidas_bateria_oracle()
                    alertas_periodo = detectar_caidas_bateria_en_bloques(
                        bloques,
                        caida_minima=reglas_caidas["caida_minima"],
                        max_horas=reglas_caidas["max_horas"],
                    )
                    total_caidas_drasticas = len(alertas_periodo)
                    detalle_alertas_completo = True
                except Exception:
                    # Si no están disponibles las reglas, se conserva el
                    # resumen oficial para que el panel siga funcionando.
                    total_caidas_drasticas = resumen_alerta_bateria.total_caidas
                    alertas_periodo = construir_alertas_periodo_desde_resumen(
                        resumen_alerta_bateria
                    )
            else:
                total_caidas_drasticas = 0
                clase_alertas_periodo = "tarjeta-neutra"
                alertas_periodo = []

        elif not mensaje:
            mensaje = "No se encontraron registros para el AMID ingresado."

    return {
        "amid": amid,
        "dias": dias,
        "hora_inicio": hora_inicio,
        "hora_fin": hora_fin,
        "ultimo_registro": ultimo_registro,
        "columnas_horas": columnas_horas,
        "tabla_bateria": tabla_bateria,
        "datos_grafico_dia": datos_grafico_dia,
        "mensaje": mensaje,
        "horario_sugerido_aplicado": horario_sugerido_aplicado,
        "datos_grafico_periodo": datos_grafico_periodo,
        "clase_bateria_actual": clase_bateria_actual,

        "estado_descarga": estado_descarga,
        "clase_descarga": clase_descarga,

        "estado_estatus": estado_estatus,
        "clase_estado": clase_estado,

        "texto_contiene_bateria": texto_contiene_bateria,
        "clase_contiene_bateria": clase_contiene_bateria,

        "texto_error_bateria": texto_error_bateria,
        "clase_error_bateria": clase_error_bateria,

        "resumen_alerta_bateria": resumen_alerta_bateria,
        "total_caidas_drasticas": total_caidas_drasticas,
        "clase_alertas_periodo": clase_alertas_periodo,
        "alertas_periodo": alertas_periodo,
        "detalle_alertas_completo": detalle_alertas_completo,
    }


def generar_columnas_media_hora(hora_inicio="00:00", hora_fin="23:30"):
    columnas = []
    inicio = datetime.strptime(hora_inicio, "%H:%M").time()
    fin = datetime.strptime(hora_fin, "%H:%M").time()

    for hora in range(24):
        for minuto in [0, 30]:
            hora_texto = f"{hora:02d}:{minuto:02d}"
            hora_obj = datetime.strptime(hora_texto, "%H:%M").time()

            if inicio <= hora_obj <= fin:
                columnas.append(hora_texto)

    return columnas


def generar_fechas_ultimos_dias(cantidad_dias=14):
    hoy = obtener_ahora_referencia().date()
    fechas = []

    for i in range(cantidad_dias):
        fechas.append(hoy - timedelta(days=i))

    return fechas


def construir_tabla_bateria(
    bloques=None,
    cantidad_dias=14,
    hora_inicio="00:00",
    hora_fin="23:30",
    registros=None,
):
    """
    Arma la tabla visual usando bloques ya preparados por Oracle.
    Ya no calcula cercanía de registros en Python.
    """
    columnas_horas = generar_columnas_media_hora(hora_inicio, hora_fin)
    fechas = generar_fechas_ultimos_dias(cantidad_dias)

    # Compatibilidad: views.py puede llamar construir_tabla_bateria(
    # registros=registros_objetos, ... ) para el Excel. En ese caso usamos esos
    # registros como si fueran bloques ya asignados por fecha_hora.
    if bloques is None:
        bloques = registros or []

    bloques_por_fecha_hora = {}

    for bloque in bloques:
        fecha_hora_bloque = getattr(bloque, "fecha_hora_bloque", None)

        if fecha_hora_bloque is None:
            fecha_hora_bloque = getattr(bloque, "fecha_hora", None)

        if not fecha_hora_bloque:
            continue

        fecha_hora_bloque = normalizar_fecha_para_comparar(
            fecha_hora_bloque
        )

        fecha_bloque = fecha_hora_bloque.date()

        hora_bloque = getattr(bloque, "hora_bloque", None)

        if not hora_bloque:
            minuto = fecha_hora_bloque.minute
            hora = fecha_hora_bloque.hour

            if minuto < 15:
                hora_bloque = f"{hora:02d}:00"
            elif minuto < 45:
                hora_bloque = f"{hora:02d}:30"
            else:
                hora_siguiente = hora + 1

                if hora_siguiente == 24:
                    hora_bloque = "23:30"
                else:
                    hora_bloque = f"{hora_siguiente:02d}:00"

        bloques_por_fecha_hora[(fecha_bloque, hora_bloque)] = bloque

    tabla = []

    for fecha in fechas:
        fila = {
            "fecha": fecha.strftime("%d-%m-%Y"),
            "valores": [],
        }

        for hora_texto in columnas_horas:
            bloque = bloques_por_fecha_hora.get((fecha, hora_texto))

            tiene_dato = (
                getattr(bloque, "tiene_dato", True)
                if bloque
                else False
            )

            porcentaje_bateria = (
                getattr(bloque, "porcentaje_bateria", None)
                if bloque
                else None
            )

            if bloque and tiene_dato and porcentaje_bateria is not None:
                valor = formatear_bateria_entera(porcentaje_bateria)
            else:
                valor = ""

            fila["valores"].append(
                {
                    "hora": hora_texto,
                    "valor": valor,
                    "clase": obtener_clase_bateria(valor),
                }
            )

        tabla.append(fila)

    return columnas_horas, tabla


def obtener_clase_bateria(valor):
    if valor == "" or valor is None:
        return "bateria-sin-dato"

    try:
        valor = float(valor)
    except (ValueError, TypeError):
        return "bateria-sin-dato"

    if valor >= 80:
        return "bateria-alta"

    if valor >= 50:
        return "bateria-media"

    if valor >= 20:
        return "bateria-baja"

    return "bateria-critica"


def construir_datos_grafico_dia(bloques, fecha_objetivo=None):
    """
    Construye gráfico de hoy desde bloques Oracle.

    Reglas:
    - Solo considera bloques del día actual.
    - La serie real muestra todos los datos reales, incluyendo batería 0.
    - La curva esperada parte desde el primer dato real mayor a 0.
    - Si el primer dato real del día es 0, la curva esperada parte desde
      el siguiente dato mayor a 0.
    - La curva esperada descuenta 3 puntos por cada bloque de 30 minutos.
    - Si hoy no hay datos reales, retorna lista vacía.
    """
    if fecha_objetivo is None:
        fecha_objetivo = obtener_ahora_referencia().date()

    columnas_horas = generar_columnas_media_hora("00:00", "23:30")
    bloques_por_hora = {}

    for bloque in bloques:
        fecha_hora_bloque = getattr(bloque, "fecha_hora_bloque", None)

        if not fecha_hora_bloque:
            continue

        fecha_bloque = normalizar_fecha_para_comparar(
            fecha_hora_bloque
        ).date()

        if fecha_bloque != fecha_objetivo:
            continue

        hora_bloque = (
            getattr(bloque, "hora_bloque", None)
            or fecha_hora_bloque.strftime("%H:%M")
        )

        bloques_por_hora[hora_bloque] = bloque

    datos = []

    for hora_texto in columnas_horas:
        bloque = bloques_por_hora.get(hora_texto)
        bateria_real = None

        if (
            bloque
            and getattr(bloque, "tiene_dato", False)
            and getattr(bloque, "porcentaje_bateria", None) is not None
            and getattr(bloque, "porcentaje_bateria", "") != ""
        ):
            try:
                bateria_real = float(bloque.porcentaje_bateria)
            except (ValueError, TypeError):
                bateria_real = None

        datos.append(
            {
                "hora": hora_texto,
                "bateria_real": bateria_real,
                "bateria_esperada": None,
            }
        )

    indices_con_dato_real = [
        indice
        for indice, punto in enumerate(datos)
        if punto["bateria_real"] is not None
    ]

    if not indices_con_dato_real:
        return []

    indices_validos_para_curva = [
        indice
        for indice, punto in enumerate(datos)
        if punto["bateria_real"] is not None
        and punto["bateria_real"] > 0
    ]

    if indices_validos_para_curva:
        indice_inicio_curva = indices_validos_para_curva[0]
        bateria_inicio = datos[indice_inicio_curva]["bateria_real"]

        for indice in range(indice_inicio_curva, len(datos)):
            bloques_transcurridos = indice - indice_inicio_curva

            datos[indice]["bateria_esperada"] = max(
                bateria_inicio - bloques_transcurridos * 3,
                0,
            )

    primer_indice_real = indices_con_dato_real[0]
    ultimo_indice_real = indices_con_dato_real[-1]

    return datos[primer_indice_real:ultimo_indice_real + 1]


def construir_datos_grafico_periodo(tabla_bateria):
    datos = []

    tabla_ordenada = list(reversed(tabla_bateria))

    for fila in tabla_ordenada:
        fecha = fila["fecha"]

        for celda in fila["valores"]:
            valor = celda["valor"]

            if valor == "" or valor is None:
                bateria_real = None
            else:
                try:
                    bateria_real = float(valor)
                except (ValueError, TypeError):
                    bateria_real = None

            datos.append(
                {
                    "fecha": fecha,
                    "hora": celda["hora"],
                    "momento": f"{fecha} {celda['hora']}",
                    "bateria_real": bateria_real,
                }
            )

    return datos