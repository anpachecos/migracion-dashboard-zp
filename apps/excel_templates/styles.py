"""
Estilos de celda: extraccion, deduplicacion y reconstruccion.

Un archivo real tiene cientos de estilos de celda, decenas de fuentes y
rellenos. Guardar el estilo completo en cada celda seria duplicar el mismo
dato millones de veces, asi que cada pieza va a su propia tabla con un hash
unico y `xl_style` solo referencia las piezas.

El flujo es siempre el mismo:

    registro = RegistroEstilos()
    hash_estilo = registro.registrar(celda)      # al leer
    fuente, relleno, ... = registro.componer(h)  # al escribir

`RegistroEstilos` es el unico lugar que conoce la deduplicacion. Las features
solo piden el hash y lo guardan.
"""

from .colors import a_openpyxl, desde_openpyxl
from .hashing import hash_de

# Orden de los lados de un borde, para comparar siempre en el mismo orden.
LADOS_BORDE = ("left", "right", "top", "bottom")


def _texto(valor):
    """
    A un primitivo de Python, o None.

    openpyxl 3.1 devuelve descriptores propios (`Integer`, `Float`, `RGB`) en
    lugar de `int`/`float`/`str`. Son subclases de los primitivos, asi que son
    serializables, pero guardarlos tal cual romperia la comparacion con el XML
    original: un `family="2"` del archivo volveria como `2.0` y cambiaria el
    hash del estilo.
    """

    if valor is None:
        return None
    if isinstance(valor, bool):
        return bool(valor)
    if isinstance(valor, int):
        return int(valor)
    if isinstance(valor, float):
        return int(valor) if valor.is_integer() else float(valor)
    return str(valor)


# --------------------------------------------------------------------- #
# Componentes: de openpyxl a dict y de vuelta
# --------------------------------------------------------------------- #

def fuente_a_dict(fuente):
    """`Font` de openpyxl a dict plano, con el color sin resolver."""

    if fuente is None:
        return {
            "name": None,
            "sz": None,
            "b": False,
            "i": False,
            "u": None,
            "strike": False,
            "color": None,
            "vertAlign": None,
            "family": None,
            "scheme": None,
            "charset": None,
            "outline": False,
            "shadow": False,
            "condense": False,
            "extend": False,
        }

    return {
        "name": _texto(fuente.name),
        "sz": float(fuente.sz) if fuente.sz is not None else None,
        "b": bool(fuente.b),
        "i": bool(fuente.i),
        "u": _texto(fuente.u),
        "strike": bool(fuente.strike),
        "color": desde_openpyxl(fuente.color),
        "vertAlign": _texto(fuente.vertAlign),
        "family": _texto(fuente.family),
        "scheme": _texto(fuente.scheme),
        "charset": _texto(fuente.charset),
        "outline": bool(fuente.outline),
        "shadow": bool(fuente.shadow),
        "condense": bool(fuente.condense),
        "extend": bool(fuente.extend),
    }


def relleno_a_dict(relleno):
    """`PatternFill` de openpyxl a dict. Sin relleno -> kind `none`."""

    if relleno is None:
        return {"kind": "none", "patternType": None, "fgColor": None, "bgColor": None}

    if getattr(relleno, "fill_type", None) == "none":
        return {"kind": "none", "patternType": None, "fgColor": None, "bgColor": None}

    return {
        "kind": "pattern",
        "patternType": _texto(relleno.patternType),
        "fgColor": desde_openpyxl(relleno.fgColor),
        "bgColor": desde_openpyxl(relleno.bgColor),
    }


def borde_a_dict(borde):
    """`Border` de openpyxl a dict con los cuatro lados."""

    if borde is None:
        return {lado: None for lado in LADOS_BORDE}

    resultado = {}
    for lado in LADOS_BORDE:
        parte = getattr(borde, lado, None)
        if parte is None or parte.style is None:
            resultado[lado] = None
            continue
        resultado[lado] = {
            "style": parte.style,
            "color": desde_openpyxl(parte.color),
        }
    return resultado


def alineacion_a_dict(alineacion):
    """`Alignment` de openpyxl a dict."""

    if alineacion is None:
        return {
            "horizontal": None,
            "vertical": None,
            "wrapText": False,
            "indent": 0,
            "textRotation": 0,
            "shrinkToFit": False,
            "readingOrder": 0,
            "justifyLastLine": False,
        }

    return {
        "horizontal": alineacion.horizontal,
        "vertical": alineacion.vertical,
        "wrapText": bool(alineacion.wrap_text),
        "indent": int(alineacion.indent or 0),
        "textRotation": int(alineacion.text_rotation or 0),
        "shrinkToFit": bool(alineacion.shrink_to_fit),
        "readingOrder": int(alineacion.readingOrder or 0),
        "justifyLastLine": bool(alineacion.justifyLastLine),
    }


def proteccion_a_dict(proteccion):
    """`Protection` de openpyxl a dict. `locked` por defecto es True en Excel."""

    if proteccion is None:
        return {"locked": True, "hidden": False}

    return {
        "locked": True if proteccion.locked is None else bool(proteccion.locked),
        "hidden": bool(proteccion.hidden),
    }


def dict_a_fuente(datos):
    from openpyxl.styles import Font

    if not datos:
        return Font()

    return Font(
        name=datos.get("name"),
        sz=datos.get("sz"),
        bold=bool(datos.get("b")),
        italic=bool(datos.get("i")),
        underline=datos.get("u"),
        strike=bool(datos.get("strike")),
        color=a_openpyxl(datos.get("color")),
        vertAlign=datos.get("vertAlign"),
        family=datos.get("family"),
        scheme=datos.get("scheme"),
        charset=datos.get("charset"),
        outline=bool(datos.get("outline")),
        shadow=bool(datos.get("shadow")),
        condense=bool(datos.get("condense")),
        extend=bool(datos.get("extend")),
    )


def dict_a_relleno(datos):
    from openpyxl.styles import PatternFill

    # Sin relleno: `PatternFill()` sin `patternType` no escribe nada en el
    # XML, que es exactamente lo que hace Excel para una celda sin pintar.
    if not datos or datos.get("kind") != "pattern":
        return PatternFill()

    return PatternFill(
        patternType=datos.get("patternType"),
        fgColor=a_openpyxl(datos.get("fgColor")),
        bgColor=a_openpyxl(datos.get("bgColor")),
    )


def dict_a_borde(datos):
    from openpyxl.styles import Border, Side

    if not datos:
        return Border()

    lados = {}
    for lado in LADOS_BORDE:
        datos_lado = datos.get(lado)
        if not datos_lado:
            lados[lado] = Side()
            continue
        lados[lado] = Side(
            style=datos_lado.get("style"),
            color=a_openpyxl(datos_lado.get("color")),
        )

    return Border(
        left=lados["left"],
        right=lados["right"],
        top=lados["top"],
        bottom=lados["bottom"],
    )


def dict_a_alineacion(datos):
    from openpyxl.styles import Alignment

    if not datos:
        return Alignment()

    return Alignment(
        horizontal=datos.get("horizontal"),
        vertical=datos.get("vertical"),
        wrap_text=bool(datos.get("wrapText")),
        indent=int(datos.get("indent") or 0),
        text_rotation=int(datos.get("textRotation") or 0),
        shrink_to_fit=bool(datos.get("shrinkToFit")),
        readingOrder=int(datos.get("readingOrder") or 0),
        justifyLastLine=bool(datos.get("justifyLastLine")),
    )


def dict_a_proteccion(datos):
    from openpyxl.styles import Protection

    if not datos:
        return Protection()

    return Protection(
        locked=bool(datos.get("locked", True)),
        hidden=bool(datos.get("hidden", False)),
    )


# --------------------------------------------------------------------- #
# Registro con deduplicacion
# --------------------------------------------------------------------- #

class RegistroEstilos:
    """
    Acumula piezas de estilo y devuelve hashes deduplicados.

    Los hashes son deterministas: leer el mismo Excel dos veces produce los
    mismos identificadores, que es lo que permite que una captura sea
    idempotente y que los tests comparen por hash.
    """

    def __init__(self):
        self.fuentes = {}
        self.rellenos = {}
        self.bordes = {}
        self.alineaciones = {}
        self.protecciones = {}
        self.formatos = {}
        self.estilos = {}

    # -- pieces ------------------------------------------------------- #

    def registrar_fuente(self, fuente):
        datos = fuente if isinstance(fuente, dict) else fuente_a_dict(fuente)
        hash_ = hash_de(datos)
        self.fuentes[hash_] = datos
        return hash_

    def registrar_relleno(self, relleno):
        datos = relleno if isinstance(relleno, dict) else relleno_a_dict(relleno)
        hash_ = hash_de(datos)
        self.rellenos[hash_] = datos
        return hash_

    def registrar_borde(self, borde):
        datos = borde if isinstance(borde, dict) else borde_a_dict(borde)
        hash_ = hash_de(datos)
        self.bordes[hash_] = datos
        return hash_

    def registrar_alineacion(self, alineacion):
        datos = alineacion if isinstance(alineacion, dict) else alineacion_a_dict(alineacion)
        hash_ = hash_de(datos)
        self.alineaciones[hash_] = datos
        return hash_

    def registrar_proteccion(self, proteccion):
        datos = proteccion if isinstance(proteccion, dict) else proteccion_a_dict(proteccion)
        hash_ = hash_de(datos)
        self.protecciones[hash_] = datos
        return hash_

    def registrar_formato(self, formato):
        datos = str(formato) if formato is not None else "General"
        hash_ = hash_de(datos)
        self.formatos[hash_] = datos
        return hash_

    # -- estilos ------------------------------------------------------ #

    def registrar_celda(self, celda):
        """
        Registra el estilo de una celda de openpyxl y devuelve su hash.

        Se llama una vez por celda con estilo. La cache por
        `id(celda._style)` evita recalcular el hash de estilos repetidos,
        que es el caso normal: 359 estilos para 80.000 celdas.
        """

        if not hasattr(self, "_cache"):
            self._cache = {}

        marca = id(getattr(celda, "_style", celda))
        if marca in self._cache:
            return self._cache[marca]

        hash_estilo = self.registrar_componentes(
            fuente=celda.font,
            relleno=celda.fill,
            borde=celda.border,
            alineacion=celda.alignment,
            proteccion=celda.protection,
            formato=celda.number_format,
        )

        self._cache[marca] = hash_estilo
        return hash_estilo

    def registrar_componentes(self, fuente=None, relleno=None, borde=None,
                              alineacion=None, proteccion=None, formato="General"):
        """Registra las seis piezas y devuelve el hash del estilo completo."""

        hash_fuente = self.registrar_fuente(fuente)
        hash_relleno = self.registrar_relleno(relleno)
        hash_borde = self.registrar_borde(borde)
        hash_alineacion = self.registrar_alineacion(alineacion)
        hash_proteccion = self.registrar_proteccion(proteccion)
        hash_formato = self.registrar_formato(formato)

        hash_estilo = hash_de(
            {
                "font": hash_fuente,
                "fill": hash_relleno,
                "border": hash_borde,
                "alignment": hash_alineacion,
                "protection": hash_proteccion,
                "number_format": hash_formato,
            }
        )

        self.estilos[hash_estilo] = {
            "font": hash_fuente,
            "fill": hash_relleno,
            "border": hash_borde,
            "alignment": hash_alineacion,
            "protection": hash_proteccion,
            "number_format": hash_formato,
        }

        return hash_estilo

    # -- salida ------------------------------------------------------- #

    def piezas(self):
        """Todo lo acumulado, listo para que `persist` lo guarde."""

        return {
            "fonts": self.fuentes,
            "fills": self.rellenos,
            "borders": self.bordes,
            "alignments": self.alineaciones,
            "protections": self.protecciones,
            "number_formats": self.formatos,
            "styles": self.estilos,
        }

    def detalle_estilo(self, hash_estilo):
        """
        Devuelve las piezas de un hash, para clasificacion de roles.

        `roles` necesita ver la fuente y el relleno (negrita, color) sin
        consultar la base, asi que esta vista en memoria del registro.
        """

        estilos = self.estilos.get(hash_estilo)
        if estilos is None:
            return {}

        return {
            "font": self.fuentes.get(estilos["font"], {}),
            "fill": self.rellenos.get(estilos["fill"], {}),
            "border": self.bordes.get(estilos["border"], {}),
            "alignment": self.alineaciones.get(estilos["alignment"], {}),
            "protection": self.protecciones.get(estilos["protection"], {}),
            "number_format": self.formatos.get(estilos["number_format"], "General"),
        }

    @property
    def hash_default(self):
        """Hash del estilo por defecto de Excel (sin formato)."""

        return self.registrar_componentes(
            fuente={},
            relleno={},
            borde={},
            alineacion={},
            proteccion={},
            formato="General",
        )

    def componer(self, hash_estilo, piezas=None):
        """
        Devuelve la tupla de estilo de openpyxl para un hash dado.

        `piezas` es el resultado de `piezas()`; si no se pasa, usa el registro
        propio, que sirve cuando se extrae y renderiza en la misma corrida.
        """

        piezas = piezas or self.piezas()

        estilos = piezas["styles"]
        if hash_estilo not in estilos:
            return self.componer(self.hash_default, piezas)

        estilos = piezas["styles"][hash_estilo]

        return (
            dict_a_fuente(piezas["fonts"].get(estilos["font"])),
            dict_a_relleno(piezas["fills"].get(estilos["fill"])),
            dict_a_borde(piezas["borders"].get(estilos["border"])),
            dict_a_alineacion(piezas["alignments"].get(estilos["alignment"])),
            dict_a_proteccion(piezas["protections"].get(estilos["protection"])),
            piezas["number_formats"].get(estilos["number_format"], "General"),
        )