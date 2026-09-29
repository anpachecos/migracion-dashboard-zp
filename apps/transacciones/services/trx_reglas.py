"""
Punto central de reglas funcionales del módulo de Transacciones.

Aquí viven los umbrales temporales de las transacciones C2D. Las tres salidas
(Informe Interno, Mayor a 15 min y Rezagadas) se calculan siempre sobre el
mismo dataset normalizado por `trx_service`, que a su vez usa este módulo.

Regla de oro: ningun otro módulo debe volver a escribir "15", "300" o
"00:05:01" por su cuenta. Si cambia un umbral, cambia aquí.
"""

SEGUNDOS_POR_MINUTO = 60
SEGUNDOS_POR_HORA = 3600

# Una TRX es "> 15 min" solo si supera ESTE valor, nunca si lo iguala.
# 15:00 pertenece a "> 5 y <= 15 min".
UMBRAL_CORTE_MINUTOS = 15
UMBRAL_CORTE_SEGUNDOS = UMBRAL_CORTE_MINUTOS * SEGUNDOS_POR_MINUTO

CLASIFICACION_HASTA_5 = "<= 5 min"
CLASIFICACION_5_A_15 = "> 5 y <= 15 min"
CLASIFICACION_MAYOR_15 = "> 15 min"
CLASIFICACION_SIN_DATO = "Sin dato"

# ---------------------------------------------------------------------------
# Etiquetas visibles derivadas del umbral.
#
# Los textos que los usuarios ven (titulos, KPIs, encabezados) se construyen
# aqui para que cambiar UMBRAL_CORTE_MINUTOS no deje pantallas diciendo "15"
# mientras la regla ya dice otra cosa. Un valor duplicado a mano en un service
# o en un template es la forma mas facil de que la interfaz mienta.
# ---------------------------------------------------------------------------

ETIQUETA_ESTADO_UMBRAL = f"Mayor a {UMBRAL_CORTE_MINUTOS} min"
ETIQUETA_KPI_MAYOR = f"TRX > {UMBRAL_CORTE_MINUTOS} min"
ETIQUETA_MISMO_DIA_MAYOR = f"Mismo día y más de {UMBRAL_CORTE_MINUTOS} min"
ETIQUETA_DIAS_MAYOR = (
    f"Días con al menos una TRX > {UMBRAL_CORTE_MINUTOS} min"
)
ETIQUETA_COMPARATIVO_MENSUAL = (
    f"Comparativo mes a mes del porcentaje de TRX sobre "
    f"{UMBRAL_CORTE_MINUTOS} minutos."
)
ETIQUETA_DETALLE_MAYOR = f"Detalle de TRX > {UMBRAL_CORTE_MINUTOS} min"
ETIQUETA_ARIA_MAYOR = (
    f"Detalle de TRX sobre {UMBRAL_CORTE_MINUTOS} minutos"
)

# Estado de la TRX frente a las dos reglas del modulo, en orden de precedencia.
#
# `es_rezagada` exige cambio de dia calendario y `es_mayor_15` exige mismo dia,
# asi que ambos jamas son True a la vez: la precedencia ordena lo que la
# exclusividad no alcanza, que es "Sin dato" por encima de todo lo demas.
PRECEDENCIA_ESTADOS = (
    "Sin dato",
    "Rezagada",
    ETIQUETA_ESTADO_UMBRAL,
    "Dentro de rango",
)

# (clave, etiqueta, minimo_segundos, maximo_segundos, etiqueta_rango, orden)
#
# Los limites son inclusivos y estan expresados en segundos porque las reglas
# functionalmente validadas usan granularidad de segundo (5:00 vs 5:01).
TRAMOS = (
    ("hasta_5", "Hasta 5 min", 0, 300, "00:00:00-00:05:00", 1),
    ("5_a_6", "5-6", 301, 360, "00:05:01-00:06:00", 2),
    ("6_a_7", "6-7", 361, 420, "00:06:01-00:07:00", 3),
    ("7_a_8", "7-8", 421, 480, "00:07:01-00:08:00", 4),
    ("8_a_10", "8-10", 481, 600, "00:08:01-00:10:00", 5),
    ("10_a_15", "10-15", 601, 900, "00:10:01-00:15:00", 6),
    ("15_a_30", "15-30", 901, 1800, "00:15:01-00:30:00", 7),
    ("30_a_60", "30-60", 1801, 3600, "00:30:01-01:00:00", 8),
    ("1_a_2", "1-2 hrs", 3601, 7200, "01:00:01-02:00:00", 9),
    ("mas_2", "Más de 2 hrs", 7201, None, "02:00:01+", 10),
)

TRAMOS_POR_CLAVE = {tramo[0]: tramo for tramo in TRAMOS}


def clasificar(duracion_segundos):
    """
    Clasificacion resumida de la diferencia FEC_BD - FEC_TRX.

    - `<= 5 min`
    - `> 5 y <= 15 min`
    - `> 15 min`

    Exactamente 15:00 NO es "> 15 min". Un valor negativo o ausente significa
    que la TRX no tiene fechas utilizables y no se clasifica.
    """

    if duracion_segundos is None or duracion_segundos < 0:
        return CLASIFICACION_SIN_DATO

    if duracion_segundos <= 5 * SEGUNDOS_POR_MINUTO:
        return CLASIFICACION_HASTA_5

    if duracion_segundos <= UMBRAL_CORTE_SEGUNDOS:
        return CLASIFICACION_5_A_15

    return CLASIFICACION_MAYOR_15


def obtener_tramo(duracion_segundos):
    """
    Devuelve el tramo detallado que contiene la duracion exacta.

    Los limites son los validados funcionalmente: 5:00 sigue en "Hasta 5 min"
    y 5:01 ya es "5-6". Devuelve None si la duracion no es utilizable.
    """

    if duracion_segundos is None or duracion_segundos < 0:
        return None

    for clave, etiqueta, minimo, maximo, rango, orden in TRAMOS:
        if duracion_segundos < minimo:
            continue
        if maximo is None or duracion_segundos <= maximo:
            return {
                "clave": clave,
                "etiqueta": etiqueta,
                "etiqueta_rango": rango,
                "orden": orden,
            }

    return None


def formatear_duracion(duracion_segundos):
    """Duración exacta en HH:MM:SS, sin redondear."""

    if duracion_segundos is None or duracion_segundos < 0:
        return "Sin dato"

    horas, resto = divmod(int(duracion_segundos), SEGUNDOS_POR_HORA)
    minutos, segundos = divmod(resto, SEGUNDOS_POR_MINUTO)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"


def es_mismo_dia(fec_trx, fec_bd):
    """
    Indicador de mismo día calendario entre generación de la TRX y llegada a BD.

    El cambio de día manda, incluso si la diferencia temporal es minima.
    """

    if fec_trx is None or fec_bd is None:
        return False

    return fec_trx.date() == fec_bd.date()


def es_rezagada(fec_trx, fec_bd):
    """
    Una TRX es rezagada cuando DATE(FEC_TRX) != DATE(FEC_BD).

    Ejemplo: lunes 23:59 -> martes 00:01 es rezagada.
    No se aplica ningun supuesto de maximo de dias.
    """

    if fec_trx is None or fec_bd is None:
        return False

    return fec_trx.date() != fec_bd.date()


def calcular_dias_rezago(fec_trx, fec_bd):
    """
    Dias de calendario entre el día de la TRX y el día de llegada a BD.

    Devuelve 0 cuando no hay rezago. No se impone un techo: la evidencia
    revisada muestra 1 a 4 dias, pero el maximo real es desconocido.
    """

    if fec_trx is None or fec_bd is None:
        return 0

    return (fec_bd.date() - fec_trx.date()).days


def es_mayor_15_mismo_dia(fec_trx, fec_bd, duracion_segundos):
    """
    Regla "> 15 min": mismo día calendario y duracion mayor a 15 minutos.

    Si cambio el día calendario la TRX es REZAGADA y nunca "> 15 min",
    aunque la diferencia temporal sea enorme.
    """

    if duracion_segundos is None or duracion_segundos < 0:
        return False

    if not es_mismo_dia(fec_trx, fec_bd):
        return False

    return duracion_segundos > UMBRAL_CORTE_SEGUNDOS
