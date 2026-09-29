"""
Salida del análisis de TRX rezagadas.

Regla: una TRX es rezagada cuando DATE(FEC_TRX) != DATE(FEC_BD). El cambio de
día manda, incluso si la diferencia temporal es mínima (lunes 23:59 ->
martes 00:01 ya es rezagada). No se asume un máximo universal de días.

Ese filtro ya viene resuelto en `es_rezagada` y es mutuamente excluyente con
`es_mayor_15` por construcción.
"""

from apps.transacciones.services import trx_reglas, trx_service

TITULO = "Rezagadas"
DESCRIPCION = (
    "Transacciones cuyo día de registro en base de datos es distinto al día "
    "en que fueron generadas."
)


def obtener_contexto_rezagadas(request, hoy=None):
    contexto = trx_service.construir_contexto_comun(
        request,
        pestana_activa="rezagadas",
        titulo=TITULO,
        descripcion=DESCRIPCION,
        hoy=hoy,
    )

    dataset = contexto.get("dataset") or []

    detalle = [trx for trx in dataset if trx["es_rezagada"]]

    contexto["filas"] = _ordenar(detalle, contexto["filtros"])
    contexto["matriz_dia_trx_dia_bd"] = _matriz_dia_trx_dia_bd(detalle)
    contexto["resumen_por_dias_rezago"] = _resumen_por_dias_rezago(detalle)
    contexto["tendencia_por_dia"] = _tendencia_por_dia(detalle)
    contexto["analisis_por_amid"] = _analisis_por_amid(detalle)
    contexto["kpis"] = _construir_kpis(contexto, dataset, detalle)
    contexto["hay_datos"] = bool(detalle)
    contexto["zonas_preparadas"] = _zonas_preparadas()

    return contexto


def _ordenar(detalle, filtros):
    """Peores casos primero: más días de rezago y luego mayor duración."""

    limite = min(
        filtros.get("maximo_filas_detalle") or len(detalle),
        len(detalle),
    )

    ordenados = sorted(
        detalle,
        key=lambda trx: (
            -trx["dias_rezago"],
            -(trx["duracion_segundos"] or 0),
            trx["nid_contexto_opte"],
        ),
    )

    return ordenados[:limite]


def _matriz_dia_trx_dia_bd(detalle):
    """Matriz día de la TRX x día de llegada a BD."""

    matriz = {}

    for trx in detalle:
        clave = (trx["fec_trx_fecha"], trx["fec_bd_fecha"])

        if clave not in matriz:
            matriz[clave] = {
                "dia_trx": trx["fec_trx_fecha"],
                "dia_bd": trx["fec_bd_fecha"],
                "total": 0,
                "dias_rezago": trx["dias_rezago"],
            }

        matriz[clave]["total"] += 1

    return sorted(
        matriz.values(),
        key=lambda fila: (fila["dia_trx"], fila["dia_bd"]),
    )


def _resumen_por_dias_rezago(detalle):
    """Conteo por cantidad de días de rezago. No impone un máximo."""

    conteo = {}

    for trx in detalle:
        conteo[trx["dias_rezago"]] = conteo.get(trx["dias_rezago"], 0) + 1

    return [
        {
            "dias_rezago": dias,
            "total": total,
            "porcentaje": trx_service.calcular_porcentual(total, len(detalle)),
        }
        for dias, total in sorted(conteo.items())
    ]


def _tendencia_por_dia(detalle):
    """Total de rezagadas agrupadas por día de llegada a BD."""

    conteo = {}

    for trx in detalle:
        conteo.setdefault(trx["fec_bd_fecha"], []).append(trx)

    filas = []

    for dia, trxs in conteo.items():
        filas.append(
            {
                "dia": dia,
                "total": len(trxs),
                "duracion_promedio_texto": _duracion_promedio(trxs),
            }
        )

    return sorted(filas, key=lambda fila: fila["dia"])


def _duracion_promedio(trxs):
    valores = [
        trx["duracion_segundos"]
        for trx in trxs
        if trx["duracion_segundos"] is not None
    ]

    if not valores:
        return "Sin dato"

    return trx_reglas.formatear_duracion(round(sum(valores) / len(valores)))


def _analisis_por_amid(detalle):
    """Resumen por AMID: total de rezagadas y peor caso."""

    por_amid = {}

    for trx in detalle:
        amid = trx["amid"]

        if amid not in por_amid:
            por_amid[amid] = {
                "amid": amid,
                "nombre_entidad": trx["nombre_entidad"],
                "nombre_sitio": trx["nombre_sitio"],
                "total": 0,
                "maximo_dias_rezago": 0,
            }

        por_amid[amid]["total"] += 1
        por_amid[amid]["maximo_dias_rezago"] = max(
            por_amid[amid]["maximo_dias_rezago"],
            trx["dias_rezago"],
        )

    return sorted(
        por_amid.values(),
        key=lambda fila: (-fila["total"], -fila["maximo_dias_rezago"], fila["amid"]),
    )


def _construir_kpis(contexto, dataset, detalle):
    """
    KPIs de rezagadas, separando el universo real del conteo de la muestra.

    TODO(trx-001): los porcentajes, el máximo de días de rezago y el conteo de
    validadores salen de `detalle`, acotado por el tope de filas. Deben pasar a
    consultas agregadas en Oracle sobre el universo completo antes de la
    validación funcional.
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
        tarjeta("Total TRX analizados", total_muestra, detalle_muestra),
        tarjeta("TRX rezagadas", agregados.get("total_rezagadas", 0)),
        tarjeta(
            "% sobre el período",
            f"{agregados.get('porcentual_rezagadas', 0)}%",
            "Del total de la muestra",
        ),
        tarjeta(
            "Máximo de días de rezago",
            agregados.get("maximo_dias_rezago", 0),
            "Sin tope asumido",
        ),
        tarjeta(
            "Validadores con rezago",
            len({trx["amid"] for trx in detalle if trx["amid"]}),
            "AMID con al menos una rezagada",
        ),
    ]


def _zonas_preparadas():
    return [
        {
            "titulo": "Análisis mensual",
            "descripcion": "Detalle mensual de rezagadas y días de rezago.",
        },
        {
            "titulo": "Gráficos",
            "descripcion": (
                "Matriz día TRX x día llegada y tendencia diaria de rezagadas."
            ),
        },
        {
            "titulo": "Análisis por AMID",
            "descripcion": (
                "Ranking de validadores por cantidad de rezagadas y peor caso."
            ),
        },
    ]
