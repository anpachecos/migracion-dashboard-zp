"""
Salida del análisis "Mayor a 15 min".

Regla: la TRX y su llegada a BD ocurren el MISMO DÍA calendario y la
diferencia supera 15 minutos. Si cambió el día calendario, la TRX es
REZAGADA y no "> 15 min". Ese filtro ya viene resuelto en `es_mayor_15`.
"""

from apps.transacciones.services import trx_reglas, trx_service

TITULO = trx_reglas.ETIQUETA_ESTADO_UMBRAL
DESCRIPCION = (
    f"Transacciones con más de {trx_reglas.UMBRAL_CORTE_MINUTOS} minutos entre "
    "su generación y su registro en base de datos, dentro del mismo día "
    "calendario."
)


def obtener_contexto_mayor_15(request, hoy=None):
    contexto = trx_service.construir_contexto_comun(
        request,
        pestana_activa="mayor_15",
        titulo=TITULO,
        descripcion=DESCRIPCION,
        hoy=hoy,
    )

    dataset = contexto.get("dataset") or []

    detalle = [trx for trx in dataset if trx["es_mayor_15"]]

    contexto["filas"] = _ordenar(detalle, contexto["filtros"])
    contexto["matriz_validador_dia"] = _matriz_validador_dia(detalle)
    contexto["ranking_validadores"] = _ranking_validadores(detalle)
    contexto["kpis"] = _construir_kpis(contexto, dataset, detalle)
    contexto["hay_datos"] = bool(detalle)
    contexto["zonas_preparadas"] = _zonas_preparadas()

    return contexto


def _ordenar(detalle, filtros):
    """Peores casos primero: mayor duración exacta."""

    limite = min(
        filtros.get("maximo_filas_detalle") or len(detalle),
        len(detalle),
    )

    ordenados = sorted(
        detalle,
        key=lambda trx: (-(trx["duracion_segundos"] or 0), trx["nid_contexto_opte"]),
    )

    return ordenados[:limite]


def _matriz_validador_dia(detalle):
    """
    Matriz validador x día con la cantidad de TRX sobre el umbral de corte.

    Es una de las salidas pedidas para este análisis y se calcula en Python
    porque el rango de una consulta está acotado.

    TODO(trx-001): bajar esta agregación (y el ranking de abajo) a consultas
    GROUP BY en Oracle sobre el universo completo antes de la validación
    funcional.
    """

    matriz = {}

    for trx in detalle:
        dia = trx["fec_trx_fecha"]
        amid = trx["amid"]
        clave = (amid, dia)

        if clave not in matriz:
            matriz[clave] = {
                "amid": amid,
                "nombre_entidad": trx["nombre_entidad"],
                "nombre_sitio": trx["nombre_sitio"],
                "dia": dia,
                "total": 0,
                "duracion_maxima": "",
                "duracion_maxima_segundos": 0,
            }

        matriz[clave]["total"] += 1

        if (trx["duracion_segundos"] or 0) > matriz[clave]["duracion_maxima_segundos"]:
            matriz[clave]["duracion_maxima_segundos"] = trx["duracion_segundos"] or 0
            matriz[clave]["duracion_maxima"] = trx["duracion_texto"]

    filas = sorted(
        matriz.values(),
        key=lambda fila: (-fila["total"], fila["dia"], fila["amid"]),
    )

    return filas


def _ranking_validadores(detalle):
    """Ranking/priorización por AMID según jumlah de casos y peor duración."""

    por_amid = {}

    for trx in detalle:
        amid = trx["amid"]

        if amid not in por_amid:
            por_amid[amid] = {
                "amid": amid,
                "nombre_entidad": trx["nombre_entidad"],
                "nombre_sitio": trx["nombre_sitio"],
                "total": 0,
                "duracion_maxima": "",
                "duracion_maxima_segundos": 0,
                "dias": set(),
            }

        registro = por_amid[amid]
        registro["total"] += 1
        registro["dias"].add(trx["fec_trx_fecha"])

        if (trx["duracion_segundos"] or 0) > registro["duracion_maxima_segundos"]:
            registro["duracion_maxima_segundos"] = trx["duracion_segundos"] or 0
            registro["duracion_maxima"] = trx["duracion_texto"]

    filas = []

    for registro in por_amid.values():
        filas.append(
            {
                "amid": registro["amid"],
                "nombre_entidad": registro["nombre_entidad"],
                "nombre_sitio": registro["nombre_sitio"],
                "total": registro["total"],
                "duracion_maxima": registro["duracion_maxima"],
                "duracion_maxima_segundos": registro["duracion_maxima_segundos"],
                "total_dias": len(registro["dias"]),
            }
        )

    return sorted(
        filas,
        key=lambda fila: (-fila["total"], -fila["duracion_maxima_segundos"], fila["amid"]),
    )


def _construir_kpis(contexto, dataset, detalle):
    """
    KPIs del análisis, separando el universo real del conteo de la muestra.

    TODO(trx-001): el "% sobre el período", la matriz validador x día y el
    ranking salen de `detalle`, que viene acotado por el tope de filas. Antes
    de la validacion funcional deben pasar a consultas agregadas en Oracle
    sobre el universo completo; hasta entonces no son comparables contra los
    Excel de referencia.
    """

    agregados = contexto.get("agregados") or {}
    consultado = contexto.get("consultado", False)
    es_placeholder = not consultado
    total_universo = contexto.get("total_universo", 0)
    total_muestra = len(dataset)

    if es_placeholder:
        detalle_muestra = ""
    elif total_universo > total_muestra:
        detalle_muestra = (
            f"{total_muestra} de {total_universo} TRX del rango "
            f"(muestra acotada)"
        )
    else:
        detalle_muestra = "Rango completo"

    def tarjeta(etiqueta, valor, detalle_texto=""):
        return {
            "etiqueta": etiqueta,
            "valor": valor if not es_placeholder else "—",
            "detalle": detalle_texto,
            "es_placeholder": es_placeholder,
        }

    return [
        tarjeta("Total TRX del rango", total_universo, "Conteo total en Oracle"),
        tarjeta(
            "Total TRX analizados",
            total_muestra,
            detalle_muestra,
        ),
        tarjeta(trx_reglas.ETIQUETA_KPI_MAYOR, agregados.get("total_mayor_15", 0)),
        tarjeta(
            "% sobre el período",
            f"{agregados.get('porcentual_mayor_15', 0)}%",
            "Del total de la muestra",
        ),
        tarjeta(
            "Validadores afectados",
            len({trx["amid"] for trx in detalle if trx["amid"]}),
            "AMID con al menos un caso",
        ),
        tarjeta(
            "Días con comportamiento problemático",
            agregados.get("dias_problematicos", 0),
            trx_reglas.ETIQUETA_DIAS_MAYOR,
        ),
    ]


def _zonas_preparadas():
    return [
        {
            "titulo": "Análisis mensual",
            "descripcion": trx_reglas.ETIQUETA_COMPARATIVO_MENSUAL,
        },
        {
            "titulo": "Gráficos",
            "descripcion": (
                "Serie diaria de casos y matriz validador x día en formato de "
                "tabla dinámica."
            ),
        },
        {
            "titulo": "Información LAB",
            "descripcion": (
                "Cruce con el laboratorio de la ZP cuando exista la fuente "
                "validada de Zonas Pagas."
            ),
        },
    ]
