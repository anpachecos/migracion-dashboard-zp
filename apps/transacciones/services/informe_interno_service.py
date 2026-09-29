"""
Salida propia del Informe Interno ZP trxC2D.

Es el primer candidato a validar el universo del dataset común contra los
Excel de referencia (27-08-2026 y 28-08-2026). No recalcula reglas: consume las
filas ya normalizadas por `trx_service`.
"""

from datetime import datetime

from apps.transacciones.services import trx_reglas, trx_service

TITULO = "Informe Interno"
DESCRIPCION = (
    "Transacciones C2D de Zonas Pagas con su fecha de generación, llegada a "
    "base de datos, operador y sitio."
)

# Cuando está activo, el informe se limita al mismo día calendario, que es el
# universo de la query 7.6 de la guía de Roxana. Sirve para comparar ambas
# lecturas contra el Excel antes de fijar el default.
PARAMETRO_SOLO_MISMO_DIA = "solo_mismo_dia"

FECHA_MINIMA = datetime.min


def obtener_contexto_informe_interno(request, hoy=None):
    contexto = trx_service.construir_contexto_comun(
        request,
        pestana_activa="informe_interno",
        titulo=TITULO,
        descripcion=DESCRIPCION,
        hoy=hoy,
    )

    dataset = contexto.get("dataset") or []
    filtros = contexto.get("filtros") or {}

    if filtros.get(PARAMETRO_SOLO_MISMO_DIA):
        dataset = [trx for trx in dataset if trx["es_mismo_dia"]]
        contexto["solo_mismo_dia_aplicado"] = True
        contexto["querystring_solo_mismo_dia"] = trx_service.construir_querystring(
            filtros,
            solo_mismo_dia=None,
        )
    else:
        contexto["solo_mismo_dia_aplicado"] = False
        contexto["querystring_solo_mismo_dia"] = trx_service.construir_querystring(
            filtros,
            solo_mismo_dia="1",
        )

    contexto["filas"] = _ordenar(dataset, filtros)
    contexto["resumen_tramos"] = _resumen_tramos(dataset)
    contexto["kpis"] = _construir_kpis(contexto, dataset)
    contexto["hay_datos"] = bool(dataset)
    contexto["zonas_preparadas"] = _zonas_preparadas()

    return contexto


def _ordenar(dataset, filtros):
    """Ordena por día de la TRX, que es el sujeto del Informe Interno."""

    limite = min(
        filtros.get("maximo_filas_detalle") or len(dataset),
        len(dataset),
    )

    ordenados = sorted(
        dataset,
        key=lambda trx: (
            trx["fec_trx"] or FECHA_MINIMA,
            trx["nid_contexto_opte"],
        ),
    )

    return ordenados[:limite]


def _resumen_tramos(dataset):
    """Distribución por tramo detallado, ordenada por el orden de la regla."""

    conteo = {}

    for trx in dataset:
        if not trx["tramo_clave"]:
            continue
        conteo.setdefault(trx["tramo_clave"], []).append(trx)

    filas = []

    for clave, etiqueta, _, _, rango, orden in trx_reglas.TRAMOS:
        trxs = conteo.get(clave, [])
        filas.append(
            {
                "clave": clave,
                "etiqueta": etiqueta,
                "etiqueta_rango": rango,
                "orden": orden,
                "total": len(trxs),
                "porcentaje": trx_service.calcular_porcentual(
                    len(trxs), len(dataset)
                ),
            }
        )

    return filas


def _construir_kpis(contexto, dataset):
    """
    KPIs derivados del dataset común.

    No son métricas inventadas: son conteos directos de las reglas ya
    validadas. Aun así se marcan como placeholder porque todavía no existe
    paridad comprobada contra los Excel de referencia.

    TODO(trx-001): separar el universo real (`total_universo`, el COUNT(*) de
    Oracle) del conteo de la muestra. El total del rango es exacto; el resto de
    las tarjetas y los porcentajes de `_resumen_tramos` salen de `dataset`, que
    esta acotado. Antes de la validacion funcional los agregados deben pasar a
    consultas Oracle sobre el universo completo.
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

    def tarjeta(etiqueta, valor, detalle=""):
        return {
            "etiqueta": etiqueta,
            "valor": valor if not es_placeholder else "—",
            "detalle": detalle,
            "es_placeholder": es_placeholder,
        }

    return [
        tarjeta("Total TRX del rango", total_universo, "Conteo total en Oracle"),
        tarjeta(
            "Total TRX analizados",
            total_muestra,
            detalle_muestra,
        ),
        tarjeta("Validadores", agregados.get("total_validadores", 0), "AMID distintos"),
        tarjeta("Sitios", agregados.get("total_sitios", 0), "Sitios distintos"),
        tarjeta(
            "Operadores",
            agregados.get("total_operadores", 0),
            "Entidades distintas",
        ),
        tarjeta(
            "TRX rezagadas",
            agregados.get("total_rezagadas", 0),
            "Cambio de día calendario",
        ),
        tarjeta(
            trx_reglas.ETIQUETA_KPI_MAYOR,
            agregados.get("total_mayor_15", 0),
            trx_reglas.ETIQUETA_MISMO_DIA_MAYOR,
        ),
    ]


def _zonas_preparadas():
    """Zonas de la pantalla listas para las siguientes iteraciones."""

    return [
        {
            "titulo": "Gráficos",
            "descripcion": (
                "Distribución por tramo y por día. Se implementará cuando el "
                "universo del dataset esté validado contra el Excel."
            ),
        },
        {
            "titulo": "Tabla",
            "descripcion": (
                "Detalle de TRX del rango con fecha TRX, fecha BD, duración, "
                "clasificación, tramo, operador y sitio."
            ),
        },
        {
            "titulo": "Exportación",
            "descripcion": "Descarga XLSX equivalente al Informe Interno de Roxana.",
        },
    ]
