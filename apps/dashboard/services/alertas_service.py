import unicodedata

from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.core.cache import cache

from apps.dashboard.repositories import alertas_repository

ORDEN_ALERTAS_PREDETERMINADO = (
    ("prioridad", "asc"),
    ("gps", "asc"),
    ("bateria", "asc"),
    ("estatus", "asc"),
)
CAMPOS_ORDEN_ALERTAS = tuple(campo for campo, _ in ORDEN_ALERTAS_PREDETERMINADO)
DIRECCIONES_ORDEN_ALERTAS = frozenset({"asc", "desc"})
OPCIONES_NIVEL_ALERTA = (
    ("todas", "", "Todas"),
    ("critica", "CRITICA", "Crítica"),
    ("alta", "ALTA", "Alta"),
    ("advertencia", "ADVERTENCIA", "Advertencia"),
    ("ok", "OK", "OK"),
)
NIVELES_ALERTA_VALIDOS = frozenset(valor for _, valor, _ in OPCIONES_NIVEL_ALERTA if valor)
OPCIONES_ESTATUS_ALERTA = (
    ("todos", "", "Todos"),
    ("con_estatus", "CON_ESTATUS", "Con estatus"),
    ("antiguo", "ANTIGUO", "Hace más de 1 hora"),
    ("sin_estatus", "SIN_ESTATUS", "Sin estatus hoy"),
)
ESTATUS_ALERTA_VALIDOS = frozenset(valor for _, valor, _ in OPCIONES_ESTATUS_ALERTA if valor)

ALERTAS_POR_PAGINA = 10
CACHE_KEY_RESUMEN_ALERTAS = "dashboard:resumen-alertas-activos:v3"
CACHE_TIMEOUT_RESUMEN_ALERTAS = 60
CACHE_KEY_UBICACIONES_ALERTAS = "dashboard:ubicaciones-alertas:v1"
CACHE_TIMEOUT_UBICACIONES_ALERTAS = 300
UBICACION_SIN_ASIGNAR = "Sin ubicaci\u00f3n asignada"
MIN_CARACTERES_BUSQUEDA_ALERTAS = 2
LIMITE_SUGERENCIAS_ALERTAS = 15
MAX_LIMITE_SUGERENCIAS_ALERTAS = 20
AMID_MINIMO_ALERTAS = 7_500_000
AMID_MAX_DIGITOS_ALERTAS = 7


def normalizar_numero(valor, default=0):
    if valor is None:
        return default
    return valor


def normalizar_texto(valor, default=""):
    if valor is None:
        return default
    return str(valor)


def normalizar_amid_alertas(valor):
    """Valida el AMID opcional recibido desde el filtro del panel."""

    amid = str(valor or "").strip()
    if not amid:
        return ""

    if not amid.isascii() or not amid.isdigit():
        raise ValueError("El AMID debe contener solo números.")

    if len(amid) > AMID_MAX_DIGITOS_ALERTAS:
        raise ValueError("El AMID puede tener como máximo 7 dígitos.")

    if int(amid) < AMID_MINIMO_ALERTAS:
        raise ValueError("El AMID debe ser mayor o igual a 7500000.")

    return amid


def normalizar_filtro_alertas(valor, permitidos):
    """Normaliza un filtro de URL y descarta opciones desconocidas."""
    valor_normalizado = str(valor or "").strip().upper()
    return valor_normalizado if valor_normalizado in permitidos else ""


def normalizar_orden_alertas(valor):
    """Normaliza las direcciones manteniendo los cinco niveles permitidos."""

    direcciones = dict(ORDEN_ALERTAS_PREDETERMINADO)

    if isinstance(valor, str):
        elementos = []
        for fragmento in valor.split(","):
            campo, separador, direccion = fragmento.strip().partition(":")
            if separador:
                elementos.append((campo, direccion))
    else:
        elementos = valor or ()

    for elemento in elementos:
        try:
            campo, direccion = elemento
        except (TypeError, ValueError):
            continue

        campo = str(campo).strip().lower()
        direccion = str(direccion).strip().lower()
        if campo in direcciones and direccion in DIRECCIONES_ORDEN_ALERTAS:
            direcciones[campo] = direccion

    return tuple((campo, direcciones[campo]) for campo in CAMPOS_ORDEN_ALERTAS)


def serializar_orden_alertas(orden):
    """Convierte el orden validado a un valor compacto para la URL."""

    return ",".join(
        f"{campo}:{direccion}"
        for campo, direccion in normalizar_orden_alertas(orden)
    )


def alternar_direccion_orden_alertas(orden, campo_objetivo):
    """Invierte un nivel sin descartar los demás criterios de orden."""

    campo_objetivo = str(campo_objetivo or "").strip().lower()
    orden_normalizado = normalizar_orden_alertas(orden)
    if campo_objetivo not in CAMPOS_ORDEN_ALERTAS:
        return orden_normalizado

    return tuple(
        (
            campo,
            ((
                "desc" if direccion == "asc" else "asc"
            ) if campo == campo_objetivo else direccion),
        )
        for campo, direccion in orden_normalizado
    )


def construir_orden_alertas(orden):
    """Construye un ORDER BY seguro para ordenar antes de paginar."""
    return alertas_repository.construir_orden_alertas(
        normalizar_orden_alertas(orden)
    )


def construir_condicion_problema(problema):
    """Convierte un filtro de problema a una condición SQL compatible con Oracle."""
    return alertas_repository.construir_condicion_problema(problema)


def construir_condicion_estatus(estatus):
    """Convierte el filtro de último estatus a una condición SQL."""
    return alertas_repository.construir_condicion_estatus(estatus)


def calcular_estado_estatus(ultimo_estatus):
    """
    Devuelve el estado visual para la celda de último estatus.

    Criterios:
    - Con estatus: tiene estatus de hoy y fue recibido hace una hora o menos.
    - Hace más de 1 hora: tiene estatus de hoy, pero fue recibido hace más de una hora.
    - Sin estatus hoy: no tiene estatus o el último estatus no corresponde al día actual.
    """

    if ultimo_estatus is None:
        return {
            "estado_estatus": "sin_estatus",
            "texto_estatus": "Sin estatus hoy",
            "clase_estatus": "estatus-sin",
        }

    ahora = datetime.now()
    inicio_hoy = datetime.combine(ahora.date(), datetime.min.time())

    if ultimo_estatus < inicio_hoy:
        return {
            "estado_estatus": "sin_estatus",
            "texto_estatus": "Sin estatus hoy",
            "clase_estatus": "estatus-sin",
        }

    if ultimo_estatus < ahora - timedelta(hours=1):
        return {
            "estado_estatus": "estatus_antiguo",
            "texto_estatus": "Hace más de 1 hora",
            "clase_estatus": "estatus-antiguo",
        }

    return {
        "estado_estatus": "con_estatus",
        "texto_estatus": "Con estatus",
        "clase_estatus": "estatus-ok",
    }


def _armar_filtros_alertas(
    amid=None,
    ubicacion=None,
    nivel=None,
    nivel_gps=None,
    nivel_bateria=None,
    tipo_alerta=None,
    problema=None,
    estatus=None,
    solo_con_alerta=True,
    amids_excluidos=None,
    ubicaciones_excluidas=None,
):
    return alertas_repository.armar_filtros_alertas(
        amid=amid,
        ubicacion=ubicacion,
        nivel=nivel,
        nivel_gps=nivel_gps,
        nivel_bateria=nivel_bateria,
        tipo_alerta=tipo_alerta,
        problema=problema,
        estatus=estatus,
        solo_con_alerta=solo_con_alerta,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
        ubicacion_sin_asignar=UBICACION_SIN_ASIGNAR,
    )


def contar_alertas_validadores(
    amid=None,
    ubicacion=None,
    nivel=None,
    nivel_gps=None,
    nivel_bateria=None,
    tipo_alerta=None,
    problema=None,
    estatus=None,
    solo_con_alerta=True,
    amids_excluidos=None,
    ubicaciones_excluidas=None,
):
    total = alertas_repository.contar_alertas_validadores(
        UBICACION_SIN_ASIGNAR,
        amid=amid,
        ubicacion=ubicacion,
        nivel=nivel,
        nivel_gps=nivel_gps,
        nivel_bateria=nivel_bateria,
        tipo_alerta=tipo_alerta,
        problema=problema,
        estatus=estatus,
        solo_con_alerta=solo_con_alerta,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )
    return int(total) if total is not None else 0


def obtener_alertas_validadores(
    amid=None,
    ubicacion=None,
    nivel=None,
    nivel_gps=None,
    nivel_bateria=None,
    tipo_alerta=None,
    problema=None,
    estatus=None,
    solo_con_alerta=True,
    limite=500,
    offset=0,
    ordenar=True,
    orden=None,
    amids_excluidos=None,
    ubicaciones_excluidas=None,
):
    """
    Lee alertas desde USR_LAB.VW_ALERTA_VALIDADOR_ACTIVA.
    No calcula reglas. Solo consulta la tabla resumen ya calculada por Oracle.
    """

    filas = alertas_repository.obtener_alertas_validadores(
        UBICACION_SIN_ASIGNAR,
        limite=limite,
        offset=offset,
        ordenar=ordenar,
        orden=normalizar_orden_alertas(orden) if ordenar else None,
        amid=amid,
        ubicacion=ubicacion,
        nivel=nivel,
        nivel_gps=nivel_gps,
        nivel_bateria=nivel_bateria,
        tipo_alerta=tipo_alerta,
        problema=problema,
        estatus=estatus,
        solo_con_alerta=solo_con_alerta,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )

    alertas = []

    for item in filas:

        item["amid"] = normalizar_numero(item.get("amid"))
        item["ubicacion_actual"] = normalizar_texto(
            item.get("ubicacion_actual"),
            UBICACION_SIN_ASIGNAR,
        )
        item["nivel_alerta_global"] = normalizar_texto(item.get("nivel_alerta_global"), "OK")
        item["nivel_alerta_gps"] = normalizar_texto(item.get("nivel_alerta_gps"), "OK")
        item["nivel_alerta_bateria"] = normalizar_texto(item.get("nivel_alerta_bateria"), "OK")
        item["motivo_principal"] = normalizar_texto(item.get("motivo_principal"), "Sin alertas")
        item["accion_sugerida"] = normalizar_texto(item.get("accion_sugerida"), "")

        item["motivo_alerta_gps"] = normalizar_texto(item.get("motivo_alerta_gps"), "")
        item["motivo_alerta_bateria"] = normalizar_texto(item.get("motivo_alerta_bateria"), "")

        item["gps_cero_hoy"] = normalizar_numero(item.get("gps_cero_hoy"))
        item["gps_cero_hist"] = normalizar_numero(item.get("gps_cero_hist"))
        item["gps_cero_porc_hoy"] = normalizar_numero(item.get("gps_cero_porc_hoy"))
        item["gps_cero_porc_hist"] = normalizar_numero(item.get("gps_cero_porc_hist"))
        item["ultimo_gps_es_cero"] = normalizar_numero(item.get("ultimo_gps_es_cero"))
        item["racha_max_gps_cero"] = normalizar_numero(item.get("racha_max_gps_cero"))

        item["bateria_actual"] = item.get("bateria_actual")
        item["caidas_hoy"] = normalizar_numero(item.get("caidas_hoy"))
        item["caidas_hist"] = normalizar_numero(item.get("caidas_hist"))
        item["total_caidas"] = item["caidas_hist"]
        item["caidas_anteriores"] = max(
            item["caidas_hist"] - item["caidas_hoy"], 0
        )
        item["bateria_cero_hoy"] = normalizar_numero(item.get("bateria_cero_hoy"))
        item["bateria_cero_hist"] = normalizar_numero(item.get("bateria_cero_hist"))

        estado_estatus = calcular_estado_estatus(item.get("ultimo_estatus"))
        item.update(estado_estatus)
        ultimo_estatus = item.get("ultimo_estatus")
        item["texto_fecha_estatus"] = (
            ultimo_estatus.strftime("%d-%m-%Y %H:%M")
            if ultimo_estatus is not None
            else "Sin dato"
        )

        alertas.append(item)

    return alertas


def obtener_alertas_para_exportar():
    """
    Obtiene el universo completo de AMID activos para la exportacion Excel.

    La exportacion no recibe filtros del panel ni exclusiones de usuario. Solo
    se ejecuta al descargar el archivo, por lo que no agrega trabajo al render
    normal de la pagina.
    """

    total_activos = contar_alertas_validadores(solo_con_alerta=False)
    if total_activos == 0:
        return []

    return obtener_alertas_validadores(
        solo_con_alerta=False,
        limite=total_activos,
        offset=0,
        orden=ORDEN_ALERTAS_PREDETERMINADO,
    )


def obtener_ubicaciones_alertas_disponibles():
    """Ubicaciones asignadas a los AMID activos que pueden excluirse."""

    ubicaciones_cache = cache.get(CACHE_KEY_UBICACIONES_ALERTAS)
    if ubicaciones_cache is not None:
        return ubicaciones_cache

    ubicaciones = [
        str(valor)
        for valor in alertas_repository.obtener_ubicaciones_alertas_disponibles(
            UBICACION_SIN_ASIGNAR
        )
    ]

    cache.set(
        CACHE_KEY_UBICACIONES_ALERTAS,
        ubicaciones,
        CACHE_TIMEOUT_UBICACIONES_ALERTAS,
    )
    return ubicaciones


def buscar_amids_alertas(termino, limite=LIMITE_SUGERENCIAS_ALERTAS):
    """Busca AMID activos por prefijo sin cargar el catalogo completo."""

    termino = str(termino or "").strip()
    if len(termino) < MIN_CARACTERES_BUSQUEDA_ALERTAS or not termino.isdigit():
        return []

    limite = max(1, min(int(limite), MAX_LIMITE_SUGERENCIAS_ALERTAS))
    return [
        str(valor)
        for valor in alertas_repository.buscar_amids_alertas(termino, limite)
    ]


def _normalizar_termino_busqueda(valor):
    texto = unicodedata.normalize("NFD", str(valor or "").casefold())
    return "".join(
        caracter for caracter in texto if not unicodedata.combining(caracter)
    )


def buscar_ubicaciones_alertas(termino, limite=LIMITE_SUGERENCIAS_ALERTAS):
    """Filtra el catalogo cacheado de ubicaciones sin enviarlo completo al HTML."""

    termino_normalizado = _normalizar_termino_busqueda(termino).strip()
    if len(termino_normalizado) < MIN_CARACTERES_BUSQUEDA_ALERTAS:
        return []

    limite = max(1, min(int(limite), MAX_LIMITE_SUGERENCIAS_ALERTAS))
    resultados = []

    for ubicacion in obtener_ubicaciones_alertas_disponibles():
        if termino_normalizado in _normalizar_termino_busqueda(ubicacion):
            resultados.append(ubicacion)
            if len(resultados) >= limite:
                break

    return resultados


def obtener_resumen_alertas(amids_excluidos=None, ubicaciones_excluidas=None):
    """
    Totales de AMID activos para las tarjetas superiores.

    Sin preferencias usa cache compartida. Un resumen personalizado se
    consulta directamente para no mezclar los datos de usuarios distintos.
    """

    usar_cache = not amids_excluidos and not ubicaciones_excluidas
    if usar_cache:
        resumen_cache = cache.get(CACHE_KEY_RESUMEN_ALERTAS)
        if resumen_cache is not None:
            return resumen_cache

    row = alertas_repository.obtener_resumen_alertas(
        UBICACION_SIN_ASIGNAR,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )

    if not row:
        resumen = {
            "total_validadores": 0,
            "total_alertas": 0,
            "total_criticas": 0,
            "total_altas": 0,
            "total_advertencias": 0,
            "total_ok": 0,
            "total_gps": 0,
            "total_bateria": 0,
            "total_caidas_bateria": 0,
            "ultima_actualizacion": None,
        }
    else:
        resumen = {
            "total_validadores": normalizar_numero(row[0]),
            "total_alertas": normalizar_numero(row[1]),
            "total_criticas": normalizar_numero(row[2]),
            "total_altas": normalizar_numero(row[3]),
            "total_advertencias": normalizar_numero(row[4]),
            "total_ok": normalizar_numero(row[5]),
            "total_gps": normalizar_numero(row[6]),
            "total_bateria": normalizar_numero(row[7]),
            "total_caidas_bateria": normalizar_numero(row[8]),
            "ultima_actualizacion": row[9],
        }

    if usar_cache:
        cache.set(
            CACHE_KEY_RESUMEN_ALERTAS,
            resumen,
            CACHE_TIMEOUT_RESUMEN_ALERTAS,
        )
    return resumen

def construir_querystring_filtro(
    amid="",
    ubicacion="",
    nivel="",
    nivel_gps="",
    nivel_bateria="",
    tipo_alerta="",
    problema="",
    estatus="",
    mostrar_todos=False,
    nivel_override=None,
    nivel_gps_override=None,
    nivel_bateria_override=None,
    estatus_override=None,
    ubicacion_override=None,
    orden=None,
):
    params = {}

    if amid:
        params["amid"] = amid

    ubicacion_final = ubicacion_override if ubicacion_override is not None else ubicacion
    if ubicacion_final:
        params["ubicacion"] = ubicacion_final

    nivel_final = nivel_override if nivel_override is not None else nivel
    if nivel_final:
        params["nivel"] = nivel_final

    nivel_gps_final = nivel_gps_override if nivel_gps_override is not None else nivel_gps
    if nivel_gps_final:
        params["nivel_gps"] = nivel_gps_final

    nivel_bateria_final = nivel_bateria_override if nivel_bateria_override is not None else nivel_bateria
    if nivel_bateria_final:
        params["nivel_bateria"] = nivel_bateria_final

    if tipo_alerta:
        params["tipo_alerta"] = tipo_alerta

    if problema:
        params["problema"] = problema

    estatus_final = estatus_override if estatus_override is not None else estatus
    if estatus_final:
        params["estatus"] = estatus_final

    orden_normalizado = normalizar_orden_alertas(orden)
    if orden_normalizado != ORDEN_ALERTAS_PREDETERMINADO:
        params["orden"] = serializar_orden_alertas(orden_normalizado)

    if mostrar_todos or nivel_final == "OK":
        params["mostrar_todos"] = "1"

    return urlencode(params)


def obtener_contexto_alertas(request, preferencias=None):
    preferencias = preferencias or {}
    amids_excluidos = preferencias.get("amids_excluidos", [])
    ubicaciones_excluidas = preferencias.get("ubicaciones_excluidas", [])
    amid = normalizar_amid_alertas(request.GET.get("amid"))
    ubicacion = request.GET.get("ubicacion", "").strip()
    nivel = normalizar_filtro_alertas(request.GET.get("nivel"), NIVELES_ALERTA_VALIDOS)
    nivel_gps = normalizar_filtro_alertas(
        request.GET.get("nivel_gps"), NIVELES_ALERTA_VALIDOS
    )
    nivel_bateria = normalizar_filtro_alertas(
        request.GET.get("nivel_bateria"), NIVELES_ALERTA_VALIDOS
    )
    tipo_alerta = request.GET.get("tipo_alerta", "").strip().upper()
    problema = request.GET.get("problema", "").strip()
    estatus = normalizar_filtro_alertas(
        request.GET.get("estatus"), ESTATUS_ALERTA_VALIDOS
    )
    mostrar_todos = request.GET.get("mostrar_todos") == "1"
    orden = normalizar_orden_alertas(
        request.GET.get("orden", "")
    )
    page = request.GET.get("page", "1").strip()

    try:
        page_num = int(page) if page else 1
    except ValueError:
        page_num = 1

    page_num = max(page_num, 1)

    solo_con_alerta = not mostrar_todos and nivel != "OK"

    total_alertas = contar_alertas_validadores(
        amid=amid if amid else None,
        ubicacion=ubicacion if ubicacion else None,
        nivel=nivel if nivel else None,
        nivel_gps=nivel_gps if nivel_gps else None,
        nivel_bateria=nivel_bateria if nivel_bateria else None,
        tipo_alerta=tipo_alerta if tipo_alerta else None,
        problema=problema if problema else None,
        estatus=estatus if estatus else None,
        solo_con_alerta=solo_con_alerta,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )

    total_paginas = max(1, (total_alertas + ALERTAS_POR_PAGINA - 1) // ALERTAS_POR_PAGINA)

    if page_num > total_paginas:
        page_num = total_paginas

    offset = (page_num - 1) * ALERTAS_POR_PAGINA

    alertas = obtener_alertas_validadores(
        amid=amid if amid else None,
        ubicacion=ubicacion if ubicacion else None,
        nivel=nivel if nivel else None,
        nivel_gps=nivel_gps if nivel_gps else None,
        nivel_bateria=nivel_bateria if nivel_bateria else None,
        tipo_alerta=tipo_alerta if tipo_alerta else None,
        problema=problema if problema else None,
        estatus=estatus if estatus else None,
        solo_con_alerta=solo_con_alerta,
        limite=ALERTAS_POR_PAGINA,
        offset=offset,
        ordenar=True,
        orden=orden,
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )

    page_obj = {
        "numero": page_num,
        "total": total_paginas,
        "has_previous": page_num > 1,
        "has_next": page_num < total_paginas,
        "previous_page_number": page_num - 1 if page_num > 1 else None,
        "next_page_number": page_num + 1 if page_num < total_paginas else None,
        "start_index": offset + 1 if total_alertas else 0,
        "end_index": min(offset + len(alertas), total_alertas),
    }

    resumen = obtener_resumen_alertas(
        amids_excluidos=amids_excluidos,
        ubicaciones_excluidas=ubicaciones_excluidas,
    )

    querystring_sin_page = construir_querystring_filtro(
        amid=amid,
        ubicacion=ubicacion,
        nivel=nivel,
        nivel_gps=nivel_gps,
        nivel_bateria=nivel_bateria,
        tipo_alerta=tipo_alerta,
        problema=problema,
        estatus=estatus,
        mostrar_todos=mostrar_todos,
        orden=orden,
    )

    parametros_querystring = {
        "amid": amid,
        "ubicacion": ubicacion,
        "nivel": nivel,
        "nivel_gps": nivel_gps,
        "nivel_bateria": nivel_bateria,
        "tipo_alerta": tipo_alerta,
        "problema": problema,
        "estatus": estatus,
        "mostrar_todos": mostrar_todos,
        "orden": orden,
    }

    parametros_sin_ubicacion = dict(parametros_querystring)
    parametros_sin_ubicacion["ubicacion_override"] = ""
    ubicacion_limpiar = construir_querystring_filtro(**parametros_sin_ubicacion)

    def construir_opciones_encabezado(opciones, filtro_actual, nombre_override):
        resultado = []
        for clave, valor, etiqueta in opciones:
            parametros = dict(parametros_querystring)
            parametros[nombre_override] = valor
            resultado.append(
                {
                    "clave": clave,
                    "valor": valor,
                    "etiqueta": etiqueta,
                    "activo": filtro_actual == valor,
                    "querystring": construir_querystring_filtro(**parametros),
                }
            )
        return resultado

    filtros_encabezados = {
        "prioridad": construir_opciones_encabezado(OPCIONES_NIVEL_ALERTA, nivel, "nivel_override"),
        "estatus": construir_opciones_encabezado(OPCIONES_ESTATUS_ALERTA, estatus, "estatus_override"),
        "gps": construir_opciones_encabezado(OPCIONES_NIVEL_ALERTA, nivel_gps, "nivel_gps_override"),
        "bateria": construir_opciones_encabezado(OPCIONES_NIVEL_ALERTA, nivel_bateria, "nivel_bateria_override"),
    }
    cards_filtros = {
        opcion["clave"]: opcion["querystring"]
        for opcion in filtros_encabezados["prioridad"]
    }

    orden_encabezados = {}
    for campo_orden, direccion_orden in orden:
        orden_alternado = alternar_direccion_orden_alertas(orden, campo_orden)
        orden_encabezados[campo_orden] = {
            "direccion": direccion_orden,
            "simbolo": "▲" if direccion_orden == "asc" else "▼",
            "querystring": construir_querystring_filtro(
                amid=amid,
                ubicacion=ubicacion,
                nivel=nivel,
                nivel_gps=nivel_gps,
                nivel_bateria=nivel_bateria,
                tipo_alerta=tipo_alerta,
                problema=problema,
                estatus=estatus,
                mostrar_todos=mostrar_todos,
                orden=orden_alternado,
            ),
        }

    return {
        "alertas": alertas,
        "resumen_alertas": resumen,
        "filtro_amid": amid,
        "filtro_ubicacion": ubicacion,
        "filtro_nivel": nivel,
        "filtro_nivel_gps": nivel_gps,
        "filtro_nivel_bateria": nivel_bateria,
        "filtro_tipo_alerta": tipo_alerta,
        "filtro_problema": problema,
        "filtro_estatus": estatus,
        "mostrar_todos": mostrar_todos,
        "orden_serializado": serializar_orden_alertas(orden),
        "orden_encabezados": orden_encabezados,
        "filtros_encabezados": filtros_encabezados,
        "ubicacion_limpiar": ubicacion_limpiar,
        "page_obj": page_obj,
        "querystring_sin_page": querystring_sin_page,
        "cards_filtros": cards_filtros,
        "alertas_por_pagina": ALERTAS_POR_PAGINA,
    }
