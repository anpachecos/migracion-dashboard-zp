"""
Dataset común de transacciones C2D.

Este módulo es el unico lugar donde se normalizan las TRX y se calculan los
campos derivados que comparten las tres salidas:

    tiempo_diferencia = FEC_BD - FEC_TRX

Las reglas viven en `trx_reglas`. Este service no inventa reglas: las aplica y
calcula los datos de contexto (fechas, dias, duracion exacta, clasificacion,
tramo, mismo dia, rezagada, dias de rezago) una sola vez por fila.

Los servicios de cada informe (informe_interno, mayor_15, rezagadas) solo
consumen estas filas ya calculadas. No vuelven a consultar Oracle ni a
recalcular nada.
"""

from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.utils import timezone

from apps.transacciones.repositories import trx_repository
from apps.transacciones.services import trx_reglas

FORMATO_FECHA = "%Y-%m-%d"
FORMATO_FECHA_TEXTO = "%d-%m-%Y"
FORMATO_FECHA_HORA_TEXTO = "%d-%m-%Y %H:%M:%S"

ORIGEN_TRX = "trx"
ORIGEN_BD = "bd"
ORIGENES_VALIDOS = (ORIGEN_TRX, ORIGEN_BD)

MENSAJE_ORACLE_DESHABILITADO = (
    "La consulta Oracle de transacciones está deshabilitada. "
    "El panel muestra la estructura sin datos."
)
MENSAJE_SIN_RANGO = (
    "Selecciona un rango de fechas para consultar transacciones."
)

AMID_MAX_DIGITOS = 7

# Etiquetas de la navegación interna. La de "> 15 min" se deriva del umbral:
# la plantilla `_pestanas.html` no debe escribir el número del corte.
PESTANA_INFORME_INTERNO = "informe_interno"
PESTANA_MAYOR_15 = "mayor_15"
PESTANA_REZAGADAS = "rezagadas"

ETIQUETAS_PESTANA = {
    PESTANA_INFORME_INTERNO: "Informe Interno",
    PESTANA_MAYOR_15: trx_reglas.ETIQUETA_ESTADO_UMBRAL,
    PESTANA_REZAGADAS: "Rezagadas",
}

# Excel de referencia para el primer hito de validación.
# TODO(trx-001): pasar a True solo cuando el total de TRX, AMID, ZP, operador y
# clasificación temporal del sistema coincidan con estos archivos. Los KPI se
# calculan hoy sobre una muestra acotada, así que todavía no son comparables.
CONSULTAS_VALIDADAS = False
EXCEL_REFERENCIA_INFORME_INTERNO = (
    "27-08-2026 Informe_ZP_trxC2D_Interno.xlsx",
    "28-08-2026 Informe_ZP_trxC2D_Interno.xlsx",
)


def ajustar_configuracion():
    """Lee los limites configurados en settings, con defaults seguros."""

    return {
        "oracle_habilitado": bool(
            getattr(settings, "TRX_ORACLE_HABILITADO", False)
        ),
        # El piso del universo AMID tiene una sola fuente: config/settings.py.
        "amid_minimo": int(settings.TRX_AMID_MINIMO),
        "rango_maximo_dias": int(getattr(settings, "TRX_RANGO_MAXIMO_DIAS", 7)),
        "filas_por_pagina": int(getattr(settings, "TRX_FILAS_POR_PAGINA", 200)),
        "maximo_filas_detalle": int(
            getattr(settings, "TRX_MAX_FILAS_DETALLE", 2000)
        ),
        "modo_fecha_base": str(
            getattr(settings, "TRX_MODO_FECHA_BASE", ORIGEN_TRX)
        ),
    }


def normalizar_fecha(valor, etiqueta="La fecha"):
    """Convierte AAAA-MM-DD a date. Devuelve None si viene vacío."""

    texto = str(valor or "").strip()
    if not texto:
        return None

    try:
        return datetime.strptime(texto, FORMATO_FECHA).date()
    except ValueError:
        raise ValueError(f"{etiqueta} debe tener el formato AAAA-MM-DD.")


def normalizar_numero(valor, etiqueta, maximo_digitos=AMID_MAX_DIGITOS):
    """Valida un identificador numérico opcional."""

    texto = str(valor or "").strip()
    if not texto:
        return ""

    if not texto.isascii() or not texto.isdigit():
        raise ValueError(f"{etiqueta} debe contener solo números.")

    if len(texto) > maximo_digitos:
        raise ValueError(f"{etiqueta} admite como máximo {maximo_digitos} dígitos.")

    return texto


def resolver_rango(fecha_desde=None, fecha_hasta=None, dias_maximo=7, hoy=None):
    """
    Resuelve el rango inclusivo que se muestra en pantalla.

    El rango por defecto es el día de hoy. `fecha_hasta` es inclusiva para la
    persona; internamente se devuelve la exclusiva porque así se compara en
    Oracle con `<`.
    """

    hoy = hoy or timezone.localdate()

    inicio = fecha_desde or hoy
    fin = fecha_hasta or inicio

    if fin < inicio:
        raise ValueError("La fecha hasta no puede ser anterior a la fecha desde.")

    dias = (fin - inicio).days + 1

    if dias > dias_maximo:
        raise ValueError(
            f"El rango máximo permitido es de {dias_maximo} días por consulta."
        )

    return inicio, fin, fin + timedelta(days=1)


def construir_querystring(filtros, **cambios):
    """Serializa los filtros para conservar el contexto al cambiar de pestaña."""

    origen = dict(filtros)

    for clave, valor in cambios.items():
        if valor in (None, ""):
            origen.pop(clave, None)
        else:
            origen[clave] = valor

    campos = {
        "fecha_desde": origen.get("fecha_desde"),
        "fecha_hasta": origen.get("fecha_hasta"),
        "fecha": origen.get("fecha"),
        "amid": origen.get("amid"),
        "nidsitio": origen.get("nidsitio"),
        "nmodo": origen.get("nmodo"),
        "origen": origen.get("origen"),
        "solo_mismo_dia": "1" if origen.get("solo_mismo_dia") else None,
    }

    return urlencode({clave: valor for clave, valor in campos.items() if valor})


def obtener_filtros_trx(request, hoy=None):
    """
    Valida los filtros recibidos por GET.

    Acepta un día suelto (`fecha`) o un rango (`fecha_desde` / `fecha_hasta`).
    Nunca consulta Oracle: solo normaliza y acota.
    """

    configuracion = ajustar_configuracion()

    fecha = normalizar_fecha(request.GET.get("fecha"), "La fecha")

    fecha_desde = normalizar_fecha(request.GET.get("fecha_desde"), "La fecha desde")
    fecha_hasta = normalizar_fecha(request.GET.get("fecha_hasta"), "La fecha hasta")

    if fecha and not (fecha_desde or fecha_hasta):
        fecha_desde = fecha
        fecha_hasta = fecha

    inicio, fin, fin_exclusivo = resolver_rango(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        dias_maximo=configuracion["rango_maximo_dias"],
        hoy=hoy,
    )

    origen = str(request.GET.get("origen") or configuracion["modo_fecha_base"]).strip()
    if origen not in ORIGENES_VALIDOS:
        origen = configuracion["modo_fecha_base"]

    return {
        "fecha_desde": inicio,
        "fecha_hasta": fin,
        "fecha_hasta_exclusiva": fin_exclusivo,
        "dias_rango": (fin - inicio).days + 1,
        "fecha_desde_texto": inicio.strftime(FORMATO_FECHA),
        "fecha_hasta_texto": fin.strftime(FORMATO_FECHA),
        "fecha_actual": (hoy or timezone.localdate()).strftime(FORMATO_FECHA),
        "amid": normalizar_numero(request.GET.get("amid"), "El AMID"),
        "nidsitio": normalizar_numero(request.GET.get("nidsitio"), "El sitio"),
        "nmodo": normalizar_numero(request.GET.get("nmodo"), "El modo"),
        "origen": origen,
        "solo_mismo_dia": request.GET.get("solo_mismo_dia") == "1",
        "filas_por_pagina": configuracion["filas_por_pagina"],
        "maximo_filas_detalle": configuracion["maximo_filas_detalle"],
        "rango_maximo_dias": configuracion["rango_maximo_dias"],
        "oracle_habilitado": configuracion["oracle_habilitado"],
        "amid_minimo": configuracion["amid_minimo"],
    }


def formatear_fecha(valor):
    return valor.strftime(FORMATO_FECHA_TEXTO) if valor else ""


def formatear_fecha_hora(valor):
    return valor.strftime(FORMATO_FECHA_HORA_TEXTO) if valor else ""


def normalizar_texto(valor, defecto=""):
    """
    Texto limpio, o el defecto si no hay nada utilizable.

    Oracle devuelve `None` cuando el LEFT JOIN no encuentra la entidad o el
    sitio, y puede devolver cadenas de solo espacios. Los dos casos significan
    lo mismo para la pantalla, asi que se normalizan al mismo defecto.
    """

    if valor is None:
        return defecto

    texto = str(valor).strip()

    return texto or defecto


def normalizar_fila(fila):
    """
    Convierte una fila cruda del repositorio en una TRX normalizada.

    Calcula una sola vez la diferencia FEC_BD - FEC_TRX y de ahí deriva todos
    los campos funcionales. Si las fechas no permiten calcular una duración
    positiva, la TRX queda marcada como `datos_validos = False` en vez de
    inventar un valor.
    """

    fec_trx = fila.get("fec_trx")
    fec_bd = fila.get("fec_bd")

    fechas_completas = isinstance(fec_trx, datetime) and isinstance(fec_bd, datetime)

    duracion_segundos = None
    desfase_reloj = False

    if fechas_completas:
        diferencia = (fec_bd - fec_trx).total_seconds()
        if diferencia < 0:
            desfase_reloj = True
        else:
            duracion_segundos = int(diferencia)

    datos_validos = duracion_segundos is not None

    mismo_dia = trx_reglas.es_mismo_dia(fec_trx, fec_bd) if fechas_completas else False
    rezagada = (
        trx_reglas.es_rezagada(fec_trx, fec_bd) and datos_validos
    ) if fechas_completas else False
    mayor_15 = trx_reglas.es_mayor_15_mismo_dia(
        fec_trx, fec_bd, duracion_segundos
    )

    tramo = trx_reglas.obtener_tramo(duracion_segundos)
    clasificacion = trx_reglas.clasificar(duracion_segundos)

    return {
        "nid_contexto_opte": normalizar_texto(fila.get("nid_contexto_opte")),
        "num_abt": normalizar_texto(fila.get("num_abt")),
        "nid_contexto_switch": normalizar_texto(fila.get("nid_contexto_switch")),
        "nid_terminal": normalizar_texto(fila.get("nid_terminal")),
        "amid": normalizar_texto(fila.get("amid")),
        "nid_sitio": normalizar_texto(fila.get("nid_sitio")),
        "nombre_sitio": normalizar_texto(fila.get("nombre_sitio"), "Sin sitio"),
        "nid_entidad_ot": normalizar_texto(fila.get("nid_entidad_ot")),
        "nombre_entidad": normalizar_texto(
            fila.get("nombre_entidad"), "Sin operador"
        ),
        "cod_tipo_transaccion": normalizar_texto(fila.get("cod_tipo_transaccion")),
        "n_modo": normalizar_texto(fila.get("n_modo")),
        "cod_proceso": normalizar_texto(fila.get("cod_proceso")),
        "estado_envio": normalizar_texto(fila.get("estado_envio")),
        "fec_trx": fec_trx,
        "fec_bd": fec_bd,
        "fec_trx_texto": formatear_fecha_hora(fec_trx),
        "fec_bd_texto": formatear_fecha_hora(fec_bd),
        "fec_trx_fecha": formatear_fecha(fec_trx),
        "fec_bd_fecha": formatear_fecha(fec_bd),
        "duracion_segundos": duracion_segundos,
        "duracion_texto": trx_reglas.formatear_duracion(duracion_segundos),
        "duracion_minutos": (
            round(duracion_segundos / trx_reglas.SEGUNDOS_POR_MINUTO, 2)
            if duracion_segundos is not None
            else None
        ),
        "clasificacion": clasificacion,
        "tramo_clave": tramo["clave"] if tramo else "",
        "tramo_etiqueta": tramo["etiqueta"] if tramo else "",
        "tramo_rango": tramo["etiqueta_rango"] if tramo else "",
        "tramo_orden": tramo["orden"] if tramo else 0,
        "es_mismo_dia": mismo_dia,
        "es_rezagada": rezagada,
        "es_mayor_15": mayor_15,
        "dias_rezago": (
            trx_reglas.calcular_dias_rezago(fec_trx, fec_bd) if rezagada else 0
        ),
        "datos_validos": datos_validos,
        "desfase_reloj": desfase_reloj,
        "estado_texto": _estado_texto(mayor_15, rezagada, datos_validos),
        "clase_estado": _clase_estado(mayor_15, rezagada, datos_validos),
    }


ESTADO_REZAGADA = "Rezagada"
ESTADO_MAYOR_15 = trx_reglas.ETIQUETA_ESTADO_UMBRAL
ESTADO_DENTRO_DE_RANGO = "Dentro de rango"
ESTADO_SIN_DATO = "Sin dato"


def _estado_texto(mayor_15, rezagada, datos_validos):
    """
    Estado de la TRX frente a las dos reglas del módulo.

    Es una lectura directa de los indicadores ya calculados, no una regla nueva.
    Existe porque la duración sola no alcanza: una rezagada de dos minutos tiene
    "<= 5 min" en verde, y eso no describe su problema real.

    La precedencia es la de `trx_reglas.PRECEDENCIA_ESTADOS`. "Sin dato" gana
    siempre porque sin duración no hay nada que afirmar; "Rezagada" va antes que
    "> 15 min" porque el cambio de día calendario es el problema dominante y,
    en todo caso, ambas reglas ya son excluyentes.
    """

    if not datos_validos:
        return ESTADO_SIN_DATO

    if rezagada:
        return ESTADO_REZAGADA

    if mayor_15:
        return ESTADO_MAYOR_15

    return ESTADO_DENTRO_DE_RANGO


def _clase_estado(mayor_15, rezagada, datos_validos):
    if not datos_validos:
        return "trx-clase-sin-dato"

    if rezagada:
        return "trx-clase-rezagada"

    if mayor_15:
        return "trx-clase-alto"

    return "trx-clase-ok"


def obtener_dataset_base(filtros):
    """
    Dataset común de TRX del rango, ya normalizado y con reglas aplicadas.

    Cuando `TRX_ORACLE_HABILITADO` esta apagado no se abre conexión: se
    devuelve el dataset vacío y un aviso, para que el panel funcione como
    mockup sin depender de Oracle.
    """

    configuracion = ajustar_configuracion()

    resultado = {
        "dataset": [],
        "total": 0,
        "consultado": False,
        "mensaje": "",
        "truncado": False,
    }

    if not configuracion["oracle_habilitado"]:
        resultado["mensaje"] = MENSAJE_ORACLE_DESHABILITADO
        return resultado

    total = trx_repository.contar_trx_base(
        fecha_desde=filtros["fecha_desde"],
        fecha_hasta=filtros["fecha_hasta_exclusiva"],
        amid=filtros["amid"] or None,
        nidsitio=filtros["nidsitio"] or None,
        nmodo=filtros["nmodo"] or None,
        origen=filtros["origen"],
        amid_minimo=filtros["amid_minimo"],
    )

    if total == 0:
        resultado["total"] = 0
        resultado["consultado"] = True
        return resultado

    maximo = min(
        filtros["filas_por_pagina"],
        configuracion["maximo_filas_detalle"],
    )

    filas = trx_repository.obtener_trx_base(
        fecha_desde=filtros["fecha_desde"],
        fecha_hasta=filtros["fecha_hasta_exclusiva"],
        limite=maximo,
        offset=0,
        amid=filtros["amid"] or None,
        nidsitio=filtros["nidsitio"] or None,
        nmodo=filtros["nmodo"] or None,
        origen=filtros["origen"],
        amid_minimo=filtros["amid_minimo"],
    )

    resultado["dataset"] = [normalizar_fila(fila) for fila in filas]
    resultado["total"] = total
    resultado["consultado"] = True
    resultado["truncado"] = total > len(filas)

    return resultado


def resumir_dataset(dataset):
    """
    Agregados derivados del dataset común, sin volver a consultar Oracle.

    Todos estos valores son consecuencia directa de las reglas ya validadas;
    no son KPIs inventados. Cada tarjeta se marca como placeholder mientras no
    exista paridad comprobada contra los Excel de referencia.

    TODO(trx-001): `total_trx` y todos los porcentajes y conteos de este
    diccionario se calculan sobre las filas que trajo `obtener_dataset_base`,
    que esta acotado por `TRX_FILAS_POR_PAGINA` / `TRX_MAX_FILAS_DETALLE`.
    Antes de la validacion funcional hay que moverlos a consultas agregadas
    sobre el universo completo (COUNT/SUM/GROUP BY en Oracle). Los KPI
    calculados solo sobre la muestra NO son comparables contra los Excel de
    referencia, y por eso `CONSULTAS_VALIDADAS` sigue en False.
    """

    rezagadas = [trx for trx in dataset if trx["es_rezagada"]]
    mayor_15 = [trx for trx in dataset if trx["es_mayor_15"]]
    inconsistentes = [trx for trx in dataset if not trx["datos_validos"]]

    dias_problematicos = {
        trx["fec_trx_fecha"] for trx in mayor_15 if trx["fec_trx_fecha"]
    }

    return {
        "total_trx": len(dataset),
        "total_validadores": len({trx["amid"] for trx in dataset if trx["amid"]}),
        "total_sitios": len(
            {trx["nombre_sitio"] for trx in dataset if trx["nombre_sitio"]}
        ),
        "total_operadores": len(
            {trx["nombre_entidad"] for trx in dataset if trx["nombre_entidad"]}
        ),
        "total_rezagadas": len(rezagadas),
        "total_mayor_15": len(mayor_15),
        "total_inconsistentes": len(inconsistentes),
        "dias_problematicos": len(dias_problematicos),
        "maximo_dias_rezago": max(
            (trx["dias_rezago"] for trx in rezagadas),
            default=0,
        ),
        "porcentual_rezagadas": calcular_porcentual(len(rezagadas), len(dataset)),
        "porcentual_mayor_15": calcular_porcentual(len(mayor_15), len(dataset)),
    }


def calcular_porcentual(parte, total):
    if not total:
        return 0.0
    return round(parte * 100 / total, 2)


def construir_contexto_comun(request, pestana_activa, titulo, descripcion, hoy=None):
    """
    Base comun de las tres pestanas: filtros validados, dataset unico y
    agregados. Cada pestana agrega solo su propia salida.
    """

    contexto = {
        "pestana_activa": pestana_activa,
        "titulo_pestana": titulo,
        "descripcion_pestana": descripcion,
        "rangos_disponibles": construir_rangos_sugeridos(hoy),
        "consultas_validadas": CONSULTAS_VALIDADAS,
        "excel_referencia": EXCEL_REFERENCIA_INFORME_INTERNO,
        # Solo la fecha de cada Excel, para el aviso de validacion. La interfaz
        # no debe mostrar nombres de archivo: todavia no se puede descargar nada.
        "excel_referencia_fechas": tuple(
            texto.split(" ", 1)[0] for texto in EXCEL_REFERENCIA_INFORME_INTERNO
        ),
        # Etiquetas del umbral resueltas en `trx_reglas`, para que ningun
        # template escriba el numero del corte por su cuenta.
        "etiquetas_pestana": ETIQUETAS_PESTANA,
        "etiqueta_umbral": trx_reglas.ETIQUETA_ESTADO_UMBRAL,
        "etiqueta_detalle_mayor": trx_reglas.ETIQUETA_DETALLE_MAYOR,
        "etiqueta_aria_mayor": trx_reglas.ETIQUETA_ARIA_MAYOR,
        "mensaje": "",
    }

    try:
        filtros = obtener_filtros_trx(request, hoy=hoy)
    except ValueError as error:
        contexto["mensaje"] = str(error)
        contexto["dataset"] = []
        contexto["agregados"] = resumir_dataset([])
        contexto["total_universo"] = 0
        contexto["total_muestra"] = 0
        contexto["es_muestra"] = False
        contexto["consultado"] = False
        contexto["filtros"] = filtros_vacios(request, hoy)
        return contexto

    contexto["filtros"] = filtros
    contexto["querystring_filtros"] = construir_querystring(filtros)

    try:
        base = obtener_dataset_base(filtros)
    except Exception:
        # El panel nunca debe caerse por un fallo de Oracle: se informa y se
        # sigue mostrando la estructura.
        base = {
            "dataset": [],
            "total": 0,
            "consultado": False,
            "truncado": False,
            "mensaje": (
                "No fue posible consultar las transacciones en Oracle. "
                "Intenta nuevamente en algunos minutos."
            ),
        }

    contexto.update(
        {
            "dataset": base["dataset"],
            "total_universo": base["total"],
            "total_muestra": len(base["dataset"]),
            "es_muestra": base["truncado"],
            "consultado": base["consultado"],
            "truncado": base["truncado"],
            "mensaje": base["mensaje"],
            "agregados": resumir_dataset(base["dataset"]),
        }
    )

    return contexto


def filtros_vacios(request, hoy=None):
    """Filtros por defecto cuando la validacion falla, para no romper la UI."""

    hoy = hoy or timezone.localdate()
    fin_exclusivo = hoy + timedelta(days=1)

    return {
        "fecha_desde": hoy,
        "fecha_hasta": hoy,
        "fecha_hasta_exclusiva": fin_exclusivo,
        "dias_rango": 1,
        "fecha_desde_texto": hoy.strftime(FORMATO_FECHA),
        "fecha_hasta_texto": hoy.strftime(FORMATO_FECHA),
        "fecha_actual": hoy.strftime(FORMATO_FECHA),
        "amid": "",
        "nidsitio": "",
        "nmodo": "",
        "origen": ajustar_configuracion()["modo_fecha_base"],
        "solo_mismo_dia": False,
        "filas_por_pagina": ajustar_configuracion()["filas_por_pagina"],
        "maximo_filas_detalle": ajustar_configuracion()["maximo_filas_detalle"],
        "rango_maximo_dias": ajustar_configuracion()["rango_maximo_dias"],
        "oracle_habilitado": ajustar_configuracion()["oracle_habilitado"],
        "amid_minimo": ajustar_configuracion()["amid_minimo"],
    }


def construir_rangos_sugeridos(hoy=None):
    """Rangos cortos para picking. Nonir de meses completos sin filtro."""

    hoy = hoy or timezone.localdate()

    return [
        {
            "clave": "hoy",
            "etiqueta": "Hoy",
            "fecha_desde": hoy,
            "fecha_hasta": hoy,
        },
        {
            "clave": "ayer",
            "etiqueta": "Ayer",
            "fecha_desde": hoy - timedelta(days=1),
            "fecha_hasta": hoy - timedelta(days=1),
        },
        {
            "clave": "ultimos_7",
            "etiqueta": "Últimos 7 días",
            "fecha_desde": hoy - timedelta(days=6),
            "fecha_hasta": hoy,
        },
    ]
