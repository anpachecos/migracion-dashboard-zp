"""Metadatos de presentación para el editor de reglas de alertas.

Este módulo no clasifica alertas ni reemplaza a Oracle. Su única responsabilidad es
traducir las claves técnicas existentes a una interfaz comprensible y agrupada.
"""

SECCIONES = {
    "BATERIA": [
        ("deteccion", "Detección de caídas", "Define qué cambio entre bloques cuenta como una caída."),
        ("caidas_hoy", "Caídas de hoy", "Umbrales que determinan la severidad de las caídas recientes."),
        ("bateria_cero", "Batería en 0%", "Cantidad de bloques en cero que activa cada nivel."),
        ("historial", "Recurrencia e historial", "Señales históricas que elevan la severidad."),
    ],
    "GPS": [
        ("gps_hoy", "GPS 0,0 de hoy", "Cantidad y proporción de reportes 0,0 durante el día."),
        ("rachas", "Rachas consecutivas", "Persistencia de reportes GPS 0,0 consecutivos."),
        ("gps_hist", "Comportamiento histórico", "Recurrencia de GPS 0,0 en la ventana histórica."),
    ],
}


RANGOS_VISUALES = {
    "BATERIA": {
        "bateria_cero": [{
            "titulo": "Escala de bloques en 0% durante el día",
            "unidad": "bloques",
            "nota": "Los niveles altos y críticos también consideran el estado actual de la batería.",
            "marcadores": [
                ("BAT_CERO_HOY_ADV_MIN", "Advertencia desde", "advertencia"),
                ("BAT_CERO_HOY_ALTA_MIN", "Alta desde", "alta"),
                ("BAT_CERO_HOY_CRITICA", "Crítica desde", "critica"),
            ],
        }],
    },
    "GPS": {
        "gps_hoy": [
            {
                "titulo": "Escala por cantidad de reportes GPS 0,0",
                "unidad": "reportes",
                "nota": "Los límites máximos de cada tramo permanecen editables en las tarjetas.",
                "marcadores": [
                    ("GPS_CERO_HOY_ADV", "Advertencia desde", "advertencia"),
                    ("GPS_CERO_HOY_ALTA", "Alta desde", "alta"),
                    ("GPS_CERO_HOY_CRITICA", "Crítica desde", "critica"),
                ],
            },
            {
                "titulo": "Escala por porcentaje GPS 0,0",
                "unidad": "%",
                "maximo": 100,
                "nota": "Cada nivel exige además la muestra mínima de reportes configurada.",
                "marcadores": [
                    ("GPS_PORC_HOY_ALTA", "Alta desde", "alta"),
                    ("GPS_PORC_HOY_CRITICA", "Crítica desde", "critica"),
                ],
            },
        ],
        "rachas": [{
            "titulo": "Escala de rachas consecutivas GPS 0,0",
            "unidad": "reportes",
            "nota": "La racha debe corresponder al día actual para activar estos niveles.",
            "marcadores": [
                ("GPS_RACHA_ALTA", "Alta desde", "alta"),
                ("GPS_RACHA_CRITICA", "Crítica desde", "critica"),
            ],
        }],
    },
}

def _meta(nombre, seccion, prioridad, unidad, explicacion, *, minimo=0,
          maximo=None, paso=1):
    return {
        "nombre": nombre,
        "seccion": seccion,
        "prioridad": prioridad,
        "unidad": unidad,
        "explicacion": explicacion,
        "minimo": minimo,
        "maximo": maximo,
        "paso": paso,
        "usar_slider": maximo == 100,
    }


CATALOGO_REGLAS = {
    "BAT_CAIDA_MIN_DETECTAR": _meta(
        "Caída mínima detectable", "deteccion", "Detección", "puntos",
        "Una disminución de {valor} puntos o más puede registrarse como caída.", maximo=100,
    ),
    "BAT_CAIDA_MAX_HORAS": _meta(
        "Separación máxima entre lecturas", "deteccion", "Detección", "horas",
        "Las lecturas deben estar separadas por {valor} horas o menos.", paso=0.25,
    ),
    "BAT_CAIDA_HOY_CRITICA": _meta(
        "Caída crítica de hoy", "caidas_hoy", "Crítica", "puntos",
        "Una caída de hoy de {valor} puntos o más se considera crítica.", maximo=100,
    ),
    "BAT_CAIDA_HOY_CRITICA_CON_HIST": _meta(
        "Caída crítica con registro histórico", "caidas_hoy", "Crítica", "puntos",
        "Una caída de hoy de {valor} puntos o más es crítica cuando el historial contiene una caída; el historial incluye hoy.", maximo=100,
    ),
    "BAT_CAIDAS_HOY_CRITICA": _meta(
        "Cantidad crítica de caídas hoy", "caidas_hoy", "Crítica", "caídas",
        "Al alcanzar {valor} caídas durante el día, la alerta pasa a crítica.",
    ),
    "BAT_CAIDA_HOY_ALTA": _meta(
        "Caída alta de hoy", "caidas_hoy", "Alta", "puntos",
        "Una caída de hoy de {valor} puntos o más genera una alerta alta.", maximo=100,
    ),
    "BAT_CERO_HOY_CRITICA": _meta(
        "Persistencia crítica en 0%", "bateria_cero", "Crítica", "bloques",
        "Si la batería actual sigue en 0% y acumula {valor} bloques, la alerta es crítica.",
    ),
    "BAT_CERO_HOY_ALTA_MIN": _meta(
        "Inicio del rango alto en 0%", "bateria_cero", "Alta", "bloques",
        "La alerta alta por batería activa en 0% comienza en {valor} bloques.",
    ),
    "BAT_CERO_HOY_ALTA_MAX": _meta(
        "Fin del rango alto en 0%", "bateria_cero", "Alta", "bloques",
        "La alerta alta por batería activa en 0% llega hasta {valor} bloques.",
    ),
    "BAT_CERO_HOY_ADV_MIN": _meta(
        "Inicio de advertencia en 0%", "bateria_cero", "Advertencia", "bloques",
        "La advertencia por registros aislados en 0% comienza en {valor} bloque(s).",
    ),
    "BAT_CERO_HOY_ADV_MAX": _meta(
        "Fin de advertencia en 0%", "bateria_cero", "Advertencia", "bloques",
        "La advertencia por registros aislados en 0% llega hasta {valor} bloque(s).",
    ),
    "BAT_CAIDAS_HIST_ALTA": _meta(
        "Caídas históricas para nivel alto", "historial", "Alta", "caídas",
        "Con {valor} caídas históricas o más, la alerta de batería pasa a alta.",
    ),
    "BAT_CAIDA_MAX_HIST_ALTA": _meta(
        "Mayor caída histórica para nivel alto", "historial", "Alta", "puntos",
        "Una caída histórica máxima de {valor} puntos o más genera nivel alto.", maximo=100,
    ),
    "BAT_CERO_HIST_ADV": _meta(
        "Registros históricos en 0%", "historial", "Advertencia", "bloques",
        "Con {valor} bloques históricos en 0% o más se genera una advertencia.",
    ),
    "GPS_CERO_HOY_CRITICA": _meta(
        "Reportes 0,0 críticos hoy", "gps_hoy", "Crítica", "reportes",
        "Con {valor} reportes GPS 0,0 hoy o más, la alerta es crítica.",
    ),
    "GPS_PORC_HOY_CRITICA": _meta(
        "Porcentaje crítico de GPS 0,0", "gps_hoy", "Crítica", "%",
        "Si {valor}% o más de los reportes de hoy son 0,0, puede ser crítico.", maximo=100, paso=0.01,
    ),
    "GPS_TOTAL_HOY_CRITICA": _meta(
        "Muestra mínima para porcentaje crítico", "gps_hoy", "Crítica", "reportes",
        "El porcentaje crítico se evalúa al existir al menos {valor} reportes hoy.",
    ),
    "GPS_CERO_HOY_ALTA": _meta(
        "Inicio del rango alto de GPS 0,0", "gps_hoy", "Alta", "reportes",
        "El rango alto por cantidad de GPS 0,0 comienza en {valor} reportes.",
    ),
    "GPS_CERO_HOY_ALTA_MAX": _meta(
        "Fin del rango alto de GPS 0,0", "gps_hoy", "Alta", "reportes",
        "El rango alto por cantidad de GPS 0,0 llega hasta {valor} reportes.",
    ),
    "GPS_PORC_HOY_ALTA": _meta(
        "Porcentaje alto de GPS 0,0", "gps_hoy", "Alta", "%",
        "Si {valor}% o más de los reportes de hoy son 0,0, puede ser nivel alto.", maximo=100, paso=0.01,
    ),
    "GPS_TOTAL_HOY_ALTA": _meta(
        "Muestra mínima para porcentaje alto", "gps_hoy", "Alta", "reportes",
        "El porcentaje alto se evalúa al existir al menos {valor} reportes hoy.",
    ),
    "GPS_CERO_HOY_ADV": _meta(
        "Inicio de advertencia GPS 0,0", "gps_hoy", "Advertencia", "reportes",
        "La advertencia por GPS 0,0 aislado comienza en {valor} reporte(s).",
    ),
    "GPS_CERO_HOY_ADV_MAX": _meta(
        "Fin de advertencia GPS 0,0", "gps_hoy", "Advertencia", "reportes",
        "La advertencia por GPS 0,0 aislado llega hasta {valor} reporte(s).",
    ),
    "GPS_RACHA_CRITICA": _meta(
        "Racha crítica de GPS 0,0", "rachas", "Crítica", "reportes",
        "Una racha de {valor} reportes GPS 0,0 consecutivos hoy se considera crítica.",
    ),
    "GPS_RACHA_ALTA": _meta(
        "Racha alta de GPS 0,0", "rachas", "Alta", "reportes",
        "Una racha de {valor} reportes GPS 0,0 consecutivos hoy genera nivel alto.",
    ),
    "GPS_CERO_HIST_ADV": _meta(
        "GPS 0,0 históricos para advertencia", "gps_hist", "Advertencia", "reportes",
        "Con {valor} reportes históricos GPS 0,0 o más se genera una advertencia.",
    ),
    "GPS_PORC_HIST_ADV": _meta(
        "Porcentaje histórico para advertencia", "gps_hist", "Advertencia", "%",
        "Si {valor}% o más del historial es GPS 0,0 se genera una advertencia.", maximo=100, paso=0.01,
    ),
}


def validar_catalogo_reglas(claves_permitidas):
    """Evita que una regla nueva quede invisible o una clave obsoleta siga publicada."""
    claves_oracle = set(claves_permitidas)
    claves_catalogo = set(CATALOGO_REGLAS)
    faltantes = claves_oracle - claves_catalogo
    sobrantes = claves_catalogo - claves_oracle
    if faltantes or sobrantes:
        raise RuntimeError(
            "Catálogo visual de reglas desalineado. "
            f"Faltantes={sorted(faltantes)}; sobrantes={sorted(sobrantes)}"
        )


def construir_editor_reglas_alertas(reglas_por_categoria):
    """Enriquece la lectura existente y la agrupa sin alterar los valores Oracle."""
    editor = {}
    for categoria in ("BATERIA", "GPS"):
        reglas_por_clave = {regla["clave"]: regla for regla in reglas_por_categoria[categoria]}
        secciones = []
        for seccion_id, titulo, descripcion in SECCIONES[categoria]:
            reglas = []
            for clave, meta in CATALOGO_REGLAS.items():
                if meta["seccion"] != seccion_id or clave not in reglas_por_clave:
                    continue
                regla = {**reglas_por_clave[clave], **meta}
                regla["explicacion_actual"] = meta["explicacion"].format(
                    valor=regla["valor_numero"]
                )
                reglas.append(regla)
            if reglas:
                rangos = []
                for rango_config in RANGOS_VISUALES.get(categoria, {}).get(seccion_id, []):
                    claves = [marcador[0] for marcador in rango_config["marcadores"]]
                    if not all(clave in reglas_por_clave for clave in claves):
                        continue
                    valores = [float(reglas_por_clave[clave]["valor_numero"]) for clave in claves]
                    maximo_fijo = rango_config.get("maximo")
                    maximo_escala = maximo_fijo or max(1, max(valores) * 1.15)
                    marcadores = []
                    for (clave, etiqueta, prioridad), valor in zip(
                        rango_config["marcadores"], valores
                    ):
                        marcadores.append({
                            "clave": clave,
                            "etiqueta": etiqueta,
                            "prioridad": prioridad,
                            "valor": valor,
                            "posicion": round(min(100, (valor / maximo_escala) * 100), 2),
                        })
                    rangos.append({
                        **rango_config,
                        "maximo_escala": maximo_escala,
                        "maximo_fijo": maximo_fijo or "",
                        "marcadores": marcadores,
                    })

                secciones.append({
                    "id": seccion_id,
                    "titulo": titulo,
                    "descripcion": descripcion,
                    "reglas": reglas,
                    "rangos": rangos,
                })
        editor[categoria] = secciones
    return editor
