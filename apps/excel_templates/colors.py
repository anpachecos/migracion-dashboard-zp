"""
Colores de Excel sin resolver a RGB.

Excel admite cuatro formas de color: `rgb` (ARGB explicito), `theme`
(indice del tema del libro, mas un `tint`), `indexed` (indice de la paleta
legacy) y `auto`. Convertirlas a RGB aqui perderia informacion: al exportar,
el color volveria con el valor ya cocido y con el `tint` duplicado o
aplicado sobre un color que Excel ya aplica por su cuenta.

Por eso se guarda la forma original y se reaplica tal cual. El `theme1.xml`
crudo del libro tambien se guarda en `xl_workbook_meta.theme_xml` porque el
color de tema no significa nada sin la paleta que lo define.
"""

INDICE_TEMA_POR_DEFECTO = {
    0: "FFFFFF",  # fondo 1 (blanco)
    1: "000000",  # texto 1 (negro)
    2: "E7E6E6",  # fondo 2
    3: "44546A",  # texto 2
    4: "4472C4",  # acento 1
    5: "ED7D31",  # acento 2
    6: "A5A5A5",  # acento 3
    7: "FFC000",  # acento 4
    8: "5B9BD5",  # acento 5
    9: "70AD47",  # acento 6
    10: "0563C1",  # hipervinculo
    11: "954F72",  # hipervinculo visitado
}

# Paleta legacy de Excel (indices 0..65). El indice 64/65 son el sistema
# (ventana/texto), que openpyxl no expone; se marcan aparte.
PALETA_INDEXED = {
    0: "000000", 1: "FFFFFF", 2: "FF0000", 3: "00FF00", 4: "0000FF",
    5: "FFFF00", 6: "FF00FF", 7: "00FFFF", 8: "000000", 9: "FFFFFF",
    10: "FF0000", 11: "00FF00", 12: "0000FF", 13: "FFFF00", 14: "FF00FF",
    15: "00FFFF", 16: "800000", 17: "008000", 18: "000080", 19: "808000",
    20: "800080", 21: "008080", 22: "C0C0C0", 23: "808080", 24: "9999FF",
    25: "993366", 26: "FFFFCC", 27: "CCFFFF", 28: "660066", 29: "FF8080",
    30: "0066CC", 31: "CCCCFF", 32: "000080", 33: "FF00FF", 34: "FFFF00",
    35: "00FFFF", 36: "800080", 37: "800000", 38: "008080", 39: "0000FF",
    40: "00CCFF", 41: "CCFFFF", 42: "CCFFCC", 43: "FFFF99", 44: "99CCFF",
    45: "FF99CC", 46: "CC99FF", 47: "FFCC99", 48: "3366FF", 49: "33CCCC",
    50: "99CC00", 51: "FFCC00", 52: "FF9900", 53: "FF6600", 54: "666699",
    55: "969696", 56: "003366", 57: "339966", 58: "003300", 59: "333300",
    60: "993300", 61: "993366", 62: "333399", 63: "333333",
}


def color_vacio():
    """Color sin definir (celda por defecto)."""

    return None


# Atributos de `Color` que representan el valor en si. El orden importa: si un
# color tiene `rgb` y `theme`, manda `rgb`, que es lo que hace openpyxl.
ATRIBUTOS_COLOR = ("rgb", "theme", "indexed", "auto")


def desde_openpyxl(color):
    """
    Convierte un `Color` de openpyxl a nuestro dict, sin resolver el valor.

    Lee `color.__dict__` y no los atributos sueltos a proposito. Los
    descriptores de openpyxl (`RGB`, `Integer`, `Bool`) devuelven un objeto
    centinela con el texto del error cuando el atributo no esta puesto, y esos
    centinelas son subclases de `str`/`int`: son "verdaderos" y ademas son
    serializables, asi que comprobarlos con `if color.rgb` daria por bueno un
    color que en realidad no existe. `__dict__` solo tiene lo que el original
    traia puesto.
    """

    if color is None:
        return None

    puesto = dict(getattr(color, "__dict__", None) or {})

    tipo = None
    for nombre in ATRIBUTOS_COLOR:
        valor = puesto.get(nombre)
        # `auto` llega como False cuando no aplica y como True cuando si;
        # los otros tres tienen que estar presentes.
        if valor is None or (nombre == "auto" and not valor):
            continue
        tipo = nombre
        break

    if tipo is None:
        return None

    if tipo == "rgb":
        valor = str(puesto["rgb"])
    elif tipo == "auto":
        valor = None
    else:
        valor = int(puesto[tipo])

    resultado = {"type": tipo, "value": valor}

    tint = puesto.get("tint")
    if tint:
        # Excel guarda el tint con muchos decimales; redondear a 6 mantiene el
        # valor original casi siempre y evita hashes distintos por 1e-17.
        resultado["tint"] = round(float(tint), 6)

    return resultado


def desde_xml(atributos):
    """
    Construye un color desde los atributos de un nodo `<color>` del XML.

    Acepta tanto `<color rgb="..."/>` como `<color theme="2" tint="-0.1"/>`,
    y el orden de atributos no importa.
    """

    if not atributos:
        return None

    tint = atributos.get("tint")
    if tint is not None:
        try:
            tint = round(float(tint), 6)
        except (TypeError, ValueError):
            tint = None

    if "rgb" in atributos:
        return {"type": "rgb", "value": atributos["rgb"], **({"tint": tint} if tint else {})}

    if "theme" in atributos:
        try:
            return {"type": "theme", "value": int(atributos["theme"]), **({"tint": tint} if tint else {})}
        except (TypeError, ValueError):
            pass

    if "indexed" in atributos:
        try:
            return {"type": "indexed", "value": int(atributos["indexed"]), **({"tint": tint} if tint else {})}
        except (TypeError, ValueError):
            pass

    if "auto" in atributos:
        return {"type": "auto", "value": None, **({"tint": tint} if tint else {})}

    if tint:
        return {"type": "rgb", "value": None, "tint": tint}

    return None


def a_argumentos_xml(color):
    """Vuelve un dict de color a los atributos que espera `<color .../>`."""

    if not color:
        return None

    tipo = color.get("type")
    valor = color.get("value")
    tint = color.get("tint")

    argumentos = {}
    if tipo == "rgb":
        argumentos["rgb"] = valor or "FF000000"
    elif tipo == "theme":
        argumentos["theme"] = str(int(valor or 0))
    elif tipo == "indexed":
        argumentos["indexed"] = str(int(valor or 0))
    elif tipo == "auto":
        argumentos["auto"] = "1"

    if tint:
        argumentos["tint"] = repr(float(tint))

    return argumentos or None


def a_openpyxl(color):
    """
    Reconstruye un `Color` de openpyxl desde nuestro dict.

    Import perezoso: `extract` no necesita esta clase y `render` si, y
    mantenerlo aqui evita que un modulo dependa del otro al importarse.
    """

    from openpyxl.styles.colors import Color

    if not color:
        return None

    tipo = color.get("type")
    valor = color.get("value")
    tint = color.get("tint")

    kwargs = {}
    if tipo == "rgb":
        kwargs["rgb"] = valor or "FF000000"
    elif tipo == "theme":
        kwargs["theme"] = int(valor or 0)
    elif tipo == "indexed":
        kwargs["indexed"] = int(valor or 0)
    elif tipo == "auto":
        kwargs["auto"] = True

    if tint:
        kwargs["tint"] = float(tint)

    if not kwargs:
        return None

    return Color(**kwargs)


def a_rgb_aproximado(color):
    """
    RGB aproximado, solo para comparaciones en tests o vistas previas.

    Nunca se usa al escribir un archivo: para eso esta `a_openpyxl`.
    """

    if not color:
        return None

    tipo = color.get("type")
    valor = color.get("value")
    tint = color.get("tint") or 0.0

    if tipo == "rgb":
        base = str(valor or "FF000000").upper()
    elif tipo == "theme":
        base = INDICE_TEMA_POR_DEFECTO.get(int(valor or 0), "000000")
    elif tipo == "indexed":
        base = PALETA_INDEXED.get(int(valor or 0), "000000")
    elif tipo == "auto":
        base = "000000"
    else:
        base = "000000"

    if len(base) == 6:
        base = "FF" + base

    try:
        rojo, verde, azul = int(base[2:4], 16), int(base[4:6], 16), int(base[6:8], 16)
    except (ValueError, IndexError):
        return None

    def _aplicar_tint(componente):
        if tint == 0:
            return componente
        if tint < 0:
            return int(componente * (1 + tint))
        return int(componente + (255 - componente) * tint)

    return (
        max(0, min(255, _aplicar_tint(rojo))),
        max(0, min(255, _aplicar_tint(verde))),
        max(0, min(255, _aplicar_tint(azul))),
    )