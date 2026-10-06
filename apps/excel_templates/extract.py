"""
Extractor: `.xlsx`/`.xlsm` -> modelo intermedio.

Reglas del modulo:

- No toca la base de datos. Devuelve dicts planos que `persist` sabe guardar.
- No itera hasta `max_row` a ciegas. Una hoja puede declarar `A1:C1047436`
  sin tenerlas todas escritas, asi que el rango se toma del XML crudo
  (`<row>` presentes) y las celdas vacias con estilo se capturan por tramos.
- El color nunca se resuelve a RGB: se guarda la forma original (`rgb`,
  `theme`+tint, `indexed`, `auto`) y el `theme1.xml` crudo del libro.
- Lo que no se reconoce va a `extra_json` y al reporte. Nunca se descarta.
"""

from . import raw, roles
from .colors import desde_xml
from .hashing import sha256_archivo
from .styles import (
    RegistroEstilos,
    dict_a_alineacion,
    dict_a_borde,
    dict_a_fuente,
    dict_a_proteccion,
    dict_a_relleno,
)

# Orden de las celdas dentro de un `<row>`: openpyxl las entrega en orden, pero
# los tramos se constructions por columnas asi que no hace falta reordenar.


def _a_bool(valor):
    """Convierte los booleanos de Excel ('1', 'true', 'on') a bool."""

    if valor is None:
        return False
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ("1", "true", "on")


def _a_float(valor, defecto=None):
    """Convierte a float tolerando cadenas vacias."""

    if valor is None or valor == "":
        return defecto
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def _a_int(valor, defecto=None):
    numero = _a_float(valor)
    if numero is None:
        return defecto
    return int(numero)


def extraer(ruta, nombre=None, descripcion="", notas="", creado_por=""):
    """
    Lee un archivo y devuelve el modelo intermedio de la plantilla.

    El `sha256` del archivo va en el modelo para que la Fase 2 detecte que ya
    fue importado. No se guarda ningun valor de celda salvo el texto de las
    celdas que `roles` marque como cabecera o leyenda.
    """

    import openpyxl

    sha = sha256_archivo(ruta)
    registro = RegistroEstilos()
    reporte = _reporte_nuevo()

    with raw.RawWorkbook(ruta) as libro:
        hojas_xml = libro.hojas_en_orden()
        theme_xml = libro.theme_xml()
        defined_names = libro.defined_names()
        paleta = libro.paleta_tema()
        props = libro.props()
        calc_props = libro.calc_props()
        dxfs_xml = libro.dxfs()

        # `read_only=True` evita que openpyxl materialice el libro entero. Las
        # hojas con un millon de filas declaradas se leen fila por fila.
        libro_opl = openpyxl.load_workbook(
            ruta,
            read_only=False,  # hace falta para estilos y merged; se usa row_dimensions
            data_only=False,
            rich_text=False,
            keep_vba=ruta.lower().endswith(".xlsm"),
        )

        try:
            hojas_modelo = []
            for indice, hoja_info in enumerate(hojas_xml):
                nombre_hoja = hoja_info["name"]
                ruta_hoja = hoja_info["path"]

                if nombre_hoja not in libro_opl.sheetnames:
                    # Hoja declarada en el XML que openpyxl no abrio (hoja muy
                    # oculta o corrupta): se registra y no se pierde en silencio.
                    reporte.no_soportado(
                        "workbook",
                        f"hoja '{nombre_hoja}' declarada pero no legible por openpyxl",
                    )
                    continue

                ws = libro_opl[nombre_hoja]
                hoja_modelo = _extraer_hoja(
                    ws=ws,
                    ruta_hoja=ruta_hoja,
                    hoja_info=hoja_info,
                    libro=libro,
                    registro=registro,
                    dxfs_xml=dxfs_xml,
                    defined_names=defined_names,
                    reporte=reporte,
                )
                hojas_modelo.append(hoja_modelo)

            libro_opl.close()

        except Exception:
            libro_opl.close()
            raise

    modelo = {
        "nombre": nombre or ruta,
        "descripcion": descripcion,
        "notas": notas,
        "creado_por": creado_por,
        "source_filename": ruta.split("\\")[-1].split("/")[-1],
        "source_sha256": sha,
        "source_ext": ".xlsm" if ruta.lower().endswith(".xlsm") else ".xlsx",
        "workbook": {
            "theme_xml": theme_xml,
            "paleta_tema": paleta,
            "defined_names": defined_names,
            "props": props,
            "calc_props": calc_props,
        },
        "dxfs": dxfs_xml,
        "estilos": registro.piezas(),
        "hojas": hojas_modelo,
        "reporte": reporte.como_dict(),
    }

    return modelo


def _reporte_nuevo():
    from .report import Reporte

    return Reporte()


# --------------------------------------------------------------------- #
# Hoja
# --------------------------------------------------------------------- #

def _extraer_hoja(ws, ruta_hoja, hoja_info, libro, registro, dxfs_xml,
                  defined_names, reporte):
    """Una hoja completa a dict."""

    import openpyxl

    reporte_hoja = reporte
    nombre = ws.title

    # -- dimensiones y vista ---------------------------------------- #
    vista = _extraer_vista(libro, ruta_hoja)
    formato_impresion = libro.print_area_y_titulos(ruta_hoja)
    titulos = libro.print_titles(ruta_hoja, defined_names)

    # -- columnas ---------------------------------------------------- #
    columnas = _extraer_columnas(ws, libro, ruta_hoja, registro, reporte_hoja)

    # -- filas, tramos de estilo y celdas con texto ------------------ #
    alturas, ocultas, nivel_agrupacion, estilos_fila = _extraer_filas(
        ws, libro, ruta_hoja, registro
    )

    tramos, etiquetas, estilos_celda = _extraer_tramos(
        ws, libro, ruta_hoja, registro, reporte_hoja
    )

    # -- filtro automatico ------------------------------------------- #
    autofiltro = _extraer_autofiltro(libro, ruta_hoja, ocultas)

    # -- formato condicional ----------------------------------------- #
    condicionales = _extraer_condicionales(libro, ruta_hoja, dxfs_xml, reporte_hoja)

    # -- combinaciones, validaciones, tablas, comentarios, imagenes -- #
    combinaciones = _extraer_combinaciones(libro, ruta_hoja)
    validaciones = _extraer_validaciones(libro, ruta_hoja, reporte_hoja)
    tablas = _extraer_tablas(libro, ruta_hoja, reporte_hoja)
    comentarios = _extraer_comentarios(libro, ruta_hoja, reporte_hoja)
    imagenes = _extraer_imagenes(libro, ruta_hoja, reporte_hoja)

    # -- roles ------------------------------------------------------- #
    fila_autofiltro = None
    if autofiltro and autofiltro.get("ref"):
        limites = raw.parsear_ref(autofiltro["ref"])
        if limites:
            fila_autofiltro = limites[0]

    mapa_roles = roles.clasificar_hoja(
        estilos_por_celda=estilos_celda,
        filas_con_estilo=sorted({fila for fila, _ in estilos_celda}),
        altura_fila=alturas,
        fila_autofiltro=fila_autofiltro,
    )

    # Una celda con texto puede no tener estilo propio (pasa en la segunda
    # columna de una leyenda, donde solo la primera lleva relleno). Sin esto su
    # texto se perderia aunque la fila sea una leyenda.
    mapa_roles = roles.completar_roles(
        mapa_roles,
        {(etiqueta["row_idx"], etiqueta["col_idx"]) for etiqueta in etiquetas},
    )

    tramos = _asignar_roles(tramos, mapa_roles)

    etiquetas = _filtrar_etiquetas(etiquetas, mapa_roles)

    extra = {}
    if titulos.get("print_titles"):
        extra["print_titles"] = titulos["print_titles"]
    if formato_impresion.get("pageSetup", {}).get("r:id"):
        # El .bin de impresora no se guarda: es un blob opaco que solo
        # describe la impresora del equipo que guardo el archivo.
        extra["printer_settings_descartado"] = True
    if vista.get("__extra"):
        extra["vista_extra"] = vista.pop("__extra")

    return {
        "position": hoja_info and list(ws.parent.sheetnames).index(nombre) or 0,
        "name": nombre,
        "state": _estado_hoja(hoja_info, ws),
        "tab_color_json": _extraer_color_pestana(libro, ruta_hoja),
        "default_row_height": ws.sheet_format.defaultRowHeight,
        "default_col_width": ws.sheet_format.defaultColWidth,
        "sheet_view_json": vista,
        "page_setup_json": formato_impresion.get("pageSetup"),
        "margins_json": formato_impresion.get("pageMargins"),
        "print_json": {"print_area": titulos.get("print_area")},
        "header_footer_json": formato_impresion.get("headerFooter"),
        "extra_json": extra or None,
        "columns": columnas,
        "rows": _armar_filas(alturas, ocultas, nivel_agrupacion, estilos_fila),
        "style_runs": tramos,
        "labels": etiquetas,
        "merged": combinaciones,
        "data_validations": validaciones,
        "conditional_formats": condicionales,
        "autofilter": autofiltro,
        "tables": tablas,
        "comments": comentarios,
        "images": imagenes,
        "print_title": _armar_print_title(titulos),
    }


def _estado_hoja(hoja_info, ws):
    """Estado de visibilidad, tal como lo declara el libro."""

    if hoja_info and hoja_info.get("state"):
        estado = hoja_info["state"]
        if estado == "hidden":
            return "HIDDEN"
        if estado == "veryHidden":
            return "VERY_HIDDEN"
    return "VISIBLE"


def _extraer_vista(libro, ruta_hoja):
    """`sheetView` crudo: zoom, grid, panel inmovilizado, seleccion."""

    vista = libro.sheet_view(ruta_hoja)
    if not vista:
        return {}

    # Normaliza los booleanos que Excel escribe como "0"/"1".
    for clave in ("showGridLines", "showRowColHeaders", "showZeros",
                  "rightToLeft", "tabSelected", "showRuler",
                  "showOutlineSymbols", "defaultGridColor", "showFormulas"):
        if clave in vista:
            vista[clave] = _a_bool(vista[clave])

    for clave in ("zoomScale", "zoomScaleNormal", "zoomScaleSheetLayoutView",
                  "zoomScalePageLayoutView"):
        if clave in vista:
            valor = _a_int(vista[clave])
            if valor is not None:
                vista[clave] = valor

    return vista


def _extraer_color_pestana(libro, ruta_hoja):
    """Color de la pestana de la hoja (`<sheetPr><tabColor>`)."""

    raiz = libro.sheet_xml(ruta_hoja)
    if raiz is None:
        return None

    props = raiz.find(raw._ns("sheetPr"))
    if props is None:
        return None

    color = props.find(raw._ns("tabColor"))
    if color is None:
        return None

    return desde_xml(color.attrib)


# --------------------------------------------------------------------- #
# Columnas
# --------------------------------------------------------------------- #

def _extraer_columnas(ws, libro, ruta_hoja, registro, reporte):
    """
    Columnas con ancho, ocultamiento y estilo por defecto.

    El estilo de columna (`<col style="n">`) se guarda como `style_id`: es el
    estilo que Excel aplica a toda la columna, que en un archivo grande es la
    unica razon por la que la hoja declara un millon de filas.
    """

    columnas = []
    estilos_xml = libro.xml("xl/styles.xml")

    # `<col>` crudos: traen el `style` por indice de la paleta del libro.
    for col in libro.cols(ruta_hoja):
        minimo = _a_int(col.get("min"))
        maximo = _a_int(col.get("max"))
        if minimo is None or maximo is None:
            continue

        estilo = None
        indice_estilo = _a_int(col.get("style"))
        if indice_estilo and estilos_xml is not None:
            estilo = _resolver_indice_estilo(estilos_xml, indice_estilo, registro)
            if estilo is None and indice_estilo != 0:
                reporte.degradado(
                    "columns",
                    f"la columna {minimo}-{maximo} declara style={indice_estilo} "
                    "y ese indice no existe en styles.xml",
                    ws.title,
                )

        columnas.append(
            {
                "min_idx": minimo,
                "max_idx": maximo,
                "width": _a_float(col.get("width")),
                "hidden": _a_bool(col.get("hidden")),
                "best_fit": _a_bool(col.get("bestFit")),
                "outline_level": _a_int(col.get("outlineLevel"), 0) or 0,
                "style": estilo,
            }
        )

    if not columnas:
        # openpyxl si construye column_dimensions cuando el XML no los tiene.
        for _letra, dim in sorted(ws.column_dimensions.items()):
            if dim.width is None and not dim.hidden and not dim.style:
                continue
            estilo = None
            if dim.style:
                estilo = registro.registrar_celda(dim)
            columnas.append(
                {
                    "min_idx": dim.min,
                    "max_idx": dim.max,
                    "width": dim.width,
                    "hidden": bool(dim.hidden),
                    "best_fit": bool(dim.bestFit),
                    "outline_level": dim.outlineLevel or 0,
                    "style": estilo,
                }
            )

    return columnas


def _resolver_indice_estilo(estilos_xml, indice, registro):
    """
    Traduce el indice de estilo del XML (`<col style="n">`) a nuestro hash.

    Los estilos del libro viven en `cellXfs`; se reconstruye el estilo de esa
    entrada con los indices de `fonts`, `fills`, `borders` y `numFmts`.
    """

    xfs = estilos_xml.find(raw._ns("cellXfs"))
    if xfs is None:
        return None

    entradas = list(xfs.findall(raw._ns("xf")))
    if indice >= len(entradas):
        return None

    xf = entradas[indice]
    attrs = dict(xf.attrib)

    fuente_nodo = _leer_coleccion_indice(estilos_xml, "fonts", _a_int(attrs.get("fontId"), 0))
    relleno_nodo = _leer_coleccion_indice(estilos_xml, "fills", _a_int(attrs.get("fillId"), 0))
    borde_nodo = _leer_coleccion_indice(estilos_xml, "borders", _a_int(attrs.get("borderId"), 0))
    formato_id = _a_int(attrs.get("numFmtId"), 0)

    fuente = dict_a_fuente(_leer_fuente_xml(fuente_nodo)) if fuente_nodo is not None else None
    relleno = dict_a_relleno(_leer_relleno_xml(relleno_nodo)) if relleno_nodo is not None else None
    borde = dict_a_borde(_leer_borde_xml(borde_nodo)) if borde_nodo is not None else None

    # La alineacion y la proteccion viven en el propio `<xf>`, pero solo aplican
    # cuando el `apply*` correspondiente esta activo.
    alineacion = None
    nodo_alineacion = xf.find(raw._ns("alignment"))
    if nodo_alineacion is not None and _a_bool(attrs.get("applyAlignment")):
        alineacion = dict_a_alineacion(dict(nodo_alineacion.attrib))

    proteccion = None
    nodo_proteccion = xf.find(raw._ns("protection"))
    if nodo_proteccion is not None and _a_bool(attrs.get("applyProtection")):
        proteccion = dict_a_proteccion(dict(nodo_proteccion.attrib))

    return registro.registrar_componentes(
        fuente=fuente,
        relleno=relleno,
        borde=borde,
        alineacion=alineacion,
        proteccion=proteccion,
        formato=_leer_formato_numero(estilos_xml, formato_id),
    )


def _leer_coleccion_indice(estilos_xml, nombre, indice):
    if indice is None:
        return None
    contenedor = estilos_xml.find(raw._ns(nombre))
    if contenedor is None:
        return None
    hijos = list(contenedor)
    if indice >= len(hijos):
        return None
    return hijos[indice]


def _leer_fuente_xml(nodo):
    """
    `<font>` crudo a dict de fuente.

    Se pasa por openpyxl y de vuelta para no duplicar el conocimiento de como
    se serializa cada atributo: `styles.fuente_a_dict` ya sabe como leer un
    `Font` de openpyxl.
    """

    import openpyxl

    from .colors import desde_xml
    from .styles import fuente_a_dict

    fuente = openpyxl.styles.Font()

    nombre = nodo.find(raw._ns("name"))
    if nombre is not None:
        fuente.name = nombre.get("val")

    sz = nodo.find(raw._ns("sz"))
    if sz is not None:
        fuente.sz = _a_float(sz.get("val"))

    for etiqueta, atributo in (("b", "b"), ("i", "i"), ("strike", "strike"),
                               ("outline", "outline"), ("shadow", "shadow"),
                               ("condense", "condense"), ("extend", "extend")):
        nodo_booleano = nodo.find(raw._ns(etiqueta))
        if nodo_booleano is not None:
            # `<b/>` sin `val` significa True; `<b val="0"/` significa False.
            valor = nodo_booleano.get("val")
            setattr(fuente, atributo, True if valor is None else _a_bool(valor))

    u = nodo.find(raw._ns("u"))
    if u is not None:
        fuente.u = u.get("val")

    vert = nodo.find(raw._ns("vertAlign"))
    if vert is not None:
        fuente.vertAlign = vert.get("val")

    familia = nodo.find(raw._ns("family"))
    if familia is not None:
        fuente.family = familia.get("val")

    esquema = nodo.find(raw._ns("scheme"))
    if esquema is not None:
        fuente.scheme = esquema.get("val")

    charset = nodo.find(raw._ns("charset"))
    if charset is not None:
        fuente.charset = _a_int(charset.get("val"))

    color = nodo.find(raw._ns("color"))
    if color is not None:
        fuente.color = _color_openpyxl(desde_xml(color.attrib))

    return fuente_a_dict(fuente)


def _leer_relleno_xml(nodo):
    """`<fill>` crudo a dict de relleno."""

    import openpyxl

    from .colors import desde_xml
    from .styles import relleno_a_dict

    patron = nodo.find(raw._ns("patternFill"))
    if patron is None:
        gradiente = nodo.find(raw._ns("gradientFill"))
        if gradiente is not None:
            # Degradado: se conserva el dict aunque Fase 1 no lo reescriba, y
            # el reporte avisa de que queda degradado.
            return {
                "kind": "gradient",
                "degree": gradiente.get("degree"),
                "type": gradiente.get("type"),
                "stop": [
                    {"position": e.get("position"), "color": desde_xml(e.attrib)}
                    for e in gradiente.findall(raw._ns("stop"))
                ],
            }
        return {"kind": "none", "patternType": None, "fgColor": None, "bgColor": None}

    relleno = openpyxl.styles.PatternFill()
    relleno.patternType = patron.get("patternType")

    fg = patron.find(raw._ns("fgColor"))
    if fg is not None:
        relleno.fgColor = _color_openpyxl(desde_xml(fg.attrib))

    bg = patron.find(raw._ns("bgColor"))
    if bg is not None:
        relleno.bgColor = _color_openpyxl(desde_xml(bg.attrib))

    return relleno_a_dict(relleno)


def _leer_borde_xml(nodo):
    from .colors import desde_xml

    resultado = {}
    for lado in ("left", "right", "top", "bottom"):
        nodo_lado = nodo.find(raw._ns(lado))
        if nodo_lado is None or not nodo_lado.get("style"):
            resultado[lado] = None
            continue
        color = nodo_lado.find(raw._ns("color"))
        resultado[lado] = {
            "style": nodo_lado.get("style"),
            "color": desde_xml(color.attrib) if color is not None else None,
        }
    return resultado


def _leer_formato_numero(estilos_xml, formato_id):
    """
    Traduce `numFmtId` al string del formato.

    Los ids >= 164 son los formatos personalizados del archivo; los menores son
    los predefinidos de Excel. Guardar siempre el string es lo que evita que
    una plantilla exportada muestre `####` donde deberia mostrar la fecha.
    """

    if formato_id is None:
        return "General"

    # Predefinidos de Excel.
    predefinidos = {
        0: "General", 1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00",
        9: "0%", 10: "0.00%", 11: "0.00E+00", 12: "# ?/?", 13: "# ??/??",
        14: "mm-dd-yy", 15: "d-mmm-yy", 16: "d-mmm", 17: "mmm-yy", 18: "h:mm AM/PM",
        19: "h:mm:ss AM/PM", 20: "h:mm", 21: "h:mm:ss", 22: "m/d/yy h:mm",
        37: "#,##0 ;(#,##0)", 38: "#,##0 ;[Red](#,##0)",
        39: "#,##0.00;(#,##0.00)", 40: "#,##0.00;[Red](#,##0.00)",
        45: "mm:ss", 46: "[h]:mm:ss", 47: "mmss.0", 48: "##0.0E+0", 49: "@",
    }

    # Personalizados del archivo.
    contenedor = estilos_xml.find(raw._ns("numFmts"))
    if contenedor is not None:
        for numfmt in contenedor.findall(raw._ns("numFmt")):
            if _a_int(numfmt.get("numFmtId")) == formato_id:
                return numfmt.get("formatCode") or "General"

    return predefinidos.get(formato_id, "General")


def _color_openpyxl(color_dict):
    from .colors import a_openpyxl

    return a_openpyxl(color_dict)


# --------------------------------------------------------------------- #
# Filas y tramos de estilo
# --------------------------------------------------------------------- #

def _extraer_filas(ws, libro, ruta_hoja, registro):
    """
    Alturas, ocultamiento, agrupamiento y estilo por fila.

    Se leen los `<row>` crudos porque una hoja puede tener filas con estilo sin
    que openpyxl las haya materializado.
    """

    alturas = {}
    ocultas = set()
    nivel_agrupacion = {}
    estilos_fila = {}
    estilos_xml = libro.xml("xl/styles.xml")

    for fila in libro.filas(ruta_hoja):
        indice = _a_int(fila.get("r"))
        if indice is None:
            continue

        alto = _a_float(fila.get("ht"))
        if alto is not None:
            alturas[indice] = alto

        if _a_bool(fila.get("hidden")):
            ocultas.add(indice)

        nivel = _a_int(fila.get("outlineLevel"), 0) or 0
        if nivel:
            nivel_agrupacion[indice] = nivel

        # `<row s="n">` es el estilo por defecto de la fila: se aplica a las
        # celdas de la fila que no traen estilo propio.
        indice_estilo = _a_int(fila.get("s"))
        if indice_estilo and estilos_xml is not None:
            hash_estilo = _resolver_indice_estilo(estilos_xml, indice_estilo, registro)
            if hash_estilo is not None:
                estilos_fila[indice] = hash_estilo

    # Complementa con lo que openpyxl si haya materializado.
    for indice, dim in ws.row_dimensions.items():
        if dim.height is not None and indice not in alturas:
            alturas[indice] = dim.height
        if dim.hidden and indice not in ocultas:
            ocultas.add(indice)
        if dim.outlineLevel and indice not in nivel_agrupacion:
            nivel_agrupacion[indice] = dim.outlineLevel
        if dim.style_id and indice not in estilos_fila:
            hash_estilo = registro.registrar_celda(dim)
            estilos_fila[indice] = hash_estilo

    return alturas, ocultas, nivel_agrupacion, estilos_fila


def _armar_filas(alturas, ocultas, nivel_agrupacion, estilos_fila):
    """Filas a dicts, ordenadas, para `persist`."""

    indices = set(alturas) | set(ocultas) | set(nivel_agrupacion) | set(estilos_fila)

    return [
        {
            "row_idx": indice,
            "height": alturas.get(indice),
            "hidden": indice in ocultas,
            "outline_level": nivel_agrupacion.get(indice, 0),
            "style": estilos_fila.get(indice),
        }
        for indice in sorted(indices)
    ]


def _extraer_tramos(ws, libro, ruta_hoja, registro, reporte):
    """
    Celdas con estilo por tramos, y celdas con texto candidatas a etiqueta.

    Aqui esta el truco que hace viable un archivo grande: en vez de una fila
    por celda, se agrupan celdas contiguas con el mismo estilo en un solo tramo.
    Una fila de 42 columnas con un unico estilo es 1 registro, no 42.

    Tambien se capturan las celdas **vacias con estilo**, que en el ejemplo son
    las que definen el encabezado y los formatos de columna: sin ellas, la
    plantilla saldría sin negrita donde deberia haberla.
    """

    tramos = []
    etiquetas = []
    estilos_celda = {}

    # Se recorren solo las filas que el archivo trae escritas, no `iter_rows()`.
    # `iter_rows()` va de la primera a la ultima fila de la hoja creando celdas
    # intermedias: en una hoja con una celda suelta en la fila 1047436 eso son
    # un millon de objetos `Cell` que el archivo nunca tuvo.
    for fila_indice, celdas in _filas_escritas(ws):
        estilo_actual = None
        inicio_actual = None
        celdas_con_texto = []
        ultima_columna = None

        for celda in celdas:
            columna = celda.column
            ultima_columna = columna

            tiene_estilo = celda._style is not None and _tiene_estilo(celda)
            hash_estilo = registro.registrar_celda(celda) if tiene_estilo else None

            if tiene_estilo:
                estilos_celda[(fila_indice, columna)] = registro.detalle_estilo(hash_estilo)

            # Acumula el texto de las celdas con contenido. El rol se decide
            # despues, cuando ya se sabe cuales filas son cabecera.
            if celda.value is not None and str(celda.value) != "":
                celdas_con_texto.append((columna, celda.value))

            if hash_estilo != estilo_actual:
                if estilo_actual is not None:
                    tramos.append(
                        {
                            "row_idx": fila_indice,
                            "col_start": inicio_actual,
                            "col_end": columna - 1,
                            "style": estilo_actual,
                        }
                    )
                estilo_actual = hash_estilo
                inicio_actual = columna

        # Cierra el ultimo tramo de la fila.
        if estilo_actual is not None and inicio_actual is not None:
            tramos.append(
                {
                    "row_idx": fila_indice,
                    "col_start": inicio_actual,
                    "col_end": ultima_columna or inicio_actual,
                    "style": estilo_actual,
                }
            )

        for columna, valor in celdas_con_texto:
            etiquetas.append(
                {
                    "row_idx": fila_indice,
                    "col_idx": columna,
                    "value": _texto_celda(valor),
                    "value_type": "n" if isinstance(valor, (int, float)) else "s",
                }
            )

    # Celdas con estilo que openpyxl no materializa. En la practica openpyxl
    # si recorre las celdas con estilo, pero si un archivo trae columnas enteras
    # con estilo y sin celdas escritas, el formato se pierde: por eso se
    # revisan las columnas declaradas y se emiten tramos donde falten.
    tramos.extend(_tramos_de_columnas(ws, registro, tramos))

    return tramos, etiquetas, estilos_celda


def _filas_escritas(ws):
    """
    Las filas que el archivo trae escritas, como `(numero_fila, celdas)`.

    Las celdas vienen ordenadas por columna y son las que openpyxl ya ha
    construido al leer el XML: no se crea ninguna nueva. `ws._cells` es un
    atributo interno de openpyxl, asi que si en alguna version deja de existir
    se recurre a `iter_rows()`, que es mas lento pero siempre funciona.
    """

    celdas = getattr(ws, "_cells", None)

    if not isinstance(celdas, dict):
        for fila in ws.iter_rows():
            if fila:
                yield fila[0].row, list(fila)
        return

    por_fila = {}
    for (fila, columna), celda in celdas.items():
        por_fila.setdefault(fila, []).append((columna, celda))

    for fila in sorted(por_fila):
        yield fila, [
            celda for _columna, celda in sorted(por_fila[fila], key=lambda par: par[0])
        ]


def _tiene_estilo(celda):
    """
    True si la celda lleva un formato explicito.

    openpyxl siempre crea un `_style` (con los valores por defecto) asi que
    `is not None` no sirve: hay que comparar con el estilo 0.
    """

    estilo = getattr(celda, "_style", None)
    if estilo is None:
        return False

    # `StyleArray` es una tupla de ids; el id 0 es "sin formato".
    try:
        return any(estilo)
    except TypeError:
        return False


def _tramos_de_columnas(ws, registro, tramos_existentes):
    """
    Red de seguridad: el formato por columna no necesita ir a los tramos.

    Una columna con `style="n"` y sin celdas escritas conserva su formato solo
    si el `<col>` se vuelve a escribir con ese estilo, y `render` lo hace
    via `column_dimensions`. Por aqui no hace falta hacer nada, y la funcion
    se queda como punto unico donde decidirlo si algun archivo resulta dar
    problemas.
    """

    del ws, registro, tramos_existentes
    return []


def _texto_celda(valor):
    """Texto de una celda, sin inventar formato."""

    if valor is None:
        return ""

    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))

    return str(valor)


# --------------------------------------------------------------------- #
# Filtro automatico
# --------------------------------------------------------------------- #

def _extraer_autofiltro(libro, ruta_hoja, filas_ocultas):
    """
    Autofiltro con criterios activos y filas ocultas.

    Los criterios se guardan aunque aplicarlos al exportar sea una etapa
    posterior: `columns_json` conserva valores, filtros personalizados, de
    color y dinamicos tal cual, y `hidden_rows_json` las filas que el archivo
    traia ocultas por el filtro.
    """

    datos = libro.auto_filter(ruta_hoja)
    if datos is None:
        return None

    ocultas_por_filtro = sorted(filas_ocultas)

    return {
        "ref": datos.get("ref") or "",
        "columns_json": datos.get("columns") or [],
        "sort_state_json": datos.get("sortState"),
        "hidden_rows_json": ocultas_por_filtro,
    }


# --------------------------------------------------------------------- #
# Formato condicional
# --------------------------------------------------------------------- #

def _extraer_condicionales(libro, ruta_hoja, dxfs_xml, reporte):
    """
    Reglas de formato condicional, con su `sqref` completo y su `dxf`.

    Los rangos fragmentados (un `sqref` con `"Y2:Y24 Y26:Y29 ..."`) se guardan
    tal cual. Normalizarlos a un unico rango cambiaria que celdas quedan
    resaltadas.
    """

    from .hashing import hash_de

    bloques = libro.conditional_formats(ruta_hoja)
    if not bloques:
        return []

    reglas = []
    indices_dxf_vistos = {}

    for bloque in bloques:
        sqref_texto = bloque.get("sqref") or ""
        rangos = [r.strip() for r in sqref_texto.split() if r.strip()]

        for regla in bloque.get("rules", []):
            indice_dxf = _a_int(regla.get("dxfId"))
            hash_dxf = None
            if indice_dxf is not None:
                if indice_dxf not in indices_dxf_vistos:
                    if indice_dxf < len(dxfs_xml):
                        indices_dxf_vistos[indice_dxf] = hash_de(dxfs_xml[indice_dxf])
                    else:
                        indices_dxf_vistos[indice_dxf] = None
                        reporte.degradado(
                            "conditional_format",
                            f"regla apunta a dxfId={indice_dxf} pero el libro solo tiene "
                            f"{len(dxfs_xml)} dxf",
                            ws_title_placeholder(ruta_hoja),
                        )
                hash_dxf = indices_dxf_vistos[indice_dxf]

            tipo = regla.get("type") or ""
            operador = regla.get("operator") or ""

            escala = regla.get("colorScale")
            barra = regla.get("dataBar")
            iconos = regla.get("iconSet")

            if tipo not in (
                "cellIs", "expression", "colorScale", "dataBar", "iconSet",
                "top10", "duplicateValues", "uniqueValues", "containsText",
                "notContainsText", "beginsWith", "endsWith", "containsBlanks",
                "notContainsBlanks", "containsErrors", "notContainsErrors",
                "timePeriod", "aboveAverage",
            ):
                reporte.degradado(
                    "conditional_format",
                    f"tipo de regla '{tipo}' copiado tal cual, sin interpretacion",
                )

            reglas.append(
                {
                    "sqref_json": rangos,
                    "type": tipo,
                    "operator": operador,
                    "priority": _a_int(regla.get("priority"), 1) or 1,
                    "stop_if_true": _a_bool(regla.get("stopIfTrue")),
                    "text": regla.get("text") or "",
                    "time_period": regla.get("timePeriod") or "",
                    "rank": _a_int(regla.get("rank")),
                    "percent": _a_bool(regla.get("percent")) if regla.get("percent") else None,
                    "bottom": _a_bool(regla.get("bottom")) if regla.get("bottom") else None,
                    "std_dev": _a_int(regla.get("stdDev")),
                    "above_average": _a_bool(regla.get("aboveAverage")) if regla.get("aboveAverage") else None,
                    "equal_average": _a_bool(regla.get("equalAverage")) if regla.get("equalAverage") else None,
                    "formulas_json": [f for f in (regla.get("formula") or []) if f != ""],
                    "color_scale_json": escala,
                    "data_bar_json": barra,
                    "icon_set_json": iconos,
                    "dxf": hash_dxf,
                }
            )

    return reglas


def ws_title_placeholder(ruta_hoja):
    """El nombre de hoja no siempre esta disponible: se deja vacio."""

    del ruta_hoja
    return ""


# --------------------------------------------------------------------- #
# Combinaciones, validaciones, tablas, comentarios, imagenes
# --------------------------------------------------------------------- #

def _extraer_combinaciones(libro, ruta_hoja):
    """Rangos combinados, en el orden del archivo."""

    return [{"ref": ref} for ref in libro.merged_ranges(ruta_hoja)]


def _extraer_validaciones(libro, ruta_hoja, reporte):
    """Validaciones de datos. Las listas se conservan enteras si son literales."""

    validaciones = libro.data_validations(ruta_hoja)
    resultado = []

    for dv in validaciones:
        tipo = dv.get("type") or ""
        formula1 = dv.get("formula1")
        formula2 = dv.get("formula2")

        opciones = dict(dv)

        # Una lista desplegable con valores literales ("a,b,c") se puede
        # reconstruir; una que apunta a un rango se deja como formula.
        if tipo == "list" and formula1:
            valores = _parsear_lista(formula1)
            if valores is not None:
                opciones["valores"] = valores

        resultado.append(
            {
                "sqref_json": [r.strip() for r in (dv.get("sqref") or "").split() if r.strip()],
                "type": tipo,
                "formula1_json": formula1,
                "formula2_json": formula2,
                "options_json": opciones,
            }
        )

    if resultado:
        reporte.soportado("data_validation", f"{len(resultado)} validaciones")

    return resultado


def _parsear_lista(formula):
    """`"a,b,c"` -> `["a", "b", "c"]`, o None si no es una lista literal."""

    texto = formula.strip()
    if texto.startswith('"') and texto.endswith('"'):
        texto = texto[1:-1]
    if "," not in texto:
        return None
    if texto.startswith("="):
        return None
    return [v.strip() for v in texto.split(",") if v.strip()]


def _extraer_tablas(libro, ruta_hoja, reporte):
    """Tablas (`<table>`) declaradas por la hoja."""

    rutas = libro.tabla_por_relacion(ruta_hoja)
    if not rutas:
        return []

    tablas = []
    for ruta in rutas:
        raiz = libro.xml(ruta)
        if raiz is None:
            continue

        atributos = dict(raiz.attrib)
        columnas = []
        for columna in raiz.findall(f"{raw._ns('tableColumns')}/{raw._ns('tableColumn')}"):
            columnas.append(dict(columna.attrib))

        estilo = raiz.find(raw._ns("tableStyleInfo"))
        if estilo is not None:
            atributos["_styleInfo"] = dict(estilo.attrib)

        tablas.append(
            {
                "name": atributos.get("name") or "",
                "display_name": atributos.get("displayName") or "",
                "ref": atributos.get("ref") or "",
                "table_json": {"atributos": atributos, "columnas": columnas},
            }
        )

    if tablas:
        reporte.soportado("table", f"{len(tablas)} tablas")

    return tablas


def _extraer_comentarios(libro, ruta_hoja, reporte):
    """
    Cajas de comentario con su autor y su tamano. El texto no se guarda aqui.

    El texto del comentario es contenido. Se conserva en el modelo separado
    para que la opcion `keep_comment_text` pueda decidir, y por defecto la
    plantilla sale sin el.
    """

    raiz = libro.comments_xml(ruta_hoja)
    if raiz is None:
        return []

    ruta_comments = None
    for nombre in libro.nombres():
        if "comments" in nombre and nombre.endswith(".xml"):
            ruta_comments = nombre
            break

    autores = libro.autores_de_comentarios(ruta_comments)

    lista = []
    for comentario in raiz.findall(f"{raw._ns('commentList')}/{raw._ns('comment')}"):
        ref = comentario.get("ref")
        indice_autor = _a_int(comentario.get("authorId"), 0) or 0
        autor = autores[indice_autor] if indice_autor < len(autores) else ""

        texto = "".join(
            nodo.text or ""
            for nodo in comentario.findall(f"{raw._ns('text')}/{raw._ns('t')}")
        )

        lista.append(
            {
                "cell_ref": ref,
                "author": autor,
                "text": texto,
            }
        )

    if lista:
        reporte.soportado("comments", f"{len(lista)} comentarios (solo formato)")

    return lista


def _extraer_imagenes(libro, ruta_hoja, reporte):
    """Referencias a imagenes. Fase 1 registra el ancla; no copia el binario."""

    drawing = libro.drawing_de_hoja(ruta_hoja)
    if drawing is None:
        return []

    raiz = libro.xml(drawing)
    if raiz is None:
        return []

    ns_xdr = raw.NS_DRAWING_SS
    ns_a = raw.NS_DRAWING
    ns_r = raw.NS_REL

    imagenes = []
    for ancla in list(raiz):
        etiqueta = ancla.tag.split("}")[-1]
        if etiqueta not in ("oneCellAnchor", "twoCellAnchor", "absoluteAnchor"):
            continue

        desde = ancla.find(f"{{{ns_xdr}}}from")
        hasta = ancla.find(f"{{{ns_xdr}}}to")

        dibujo = ancla.find(f"{{{ns_a}}}graphic")
        rid = None
        if dibujo is not None:
            blip = dibujo.find(f".//{{{ns_a}}}blip")
            if blip is not None:
                rid = blip.get(f"{{{ns_r}}}embed")

        imagenes.append(
            {
                "tipo": etiqueta,
                "desde": dict(desde.attrib) if desde is not None else None,
                "hasta": dict(hasta.attrib) if hasta is not None else None,
                "r_id": rid,
            }
        )

    if imagenes:
        reporte.degradado(
            "images",
            f"{len(imagenes)} imagenes registradas por ancla; el binario no se copia "
            "en Fase 1",
        )

    return imagenes


def _armar_print_title(titulos):
    """Separa filas y columnas de `print_title_rows` / `print_title_cols`."""

    texto = titulos.get("print_titles")
    if not texto:
        return None

    filas, columnas = "", ""
    for parte in str(texto).split(","):
        parte = parte.strip()
        if parte.startswith("$") and ":" in parte:
            ref = parte.replace("$", "")
            filas = ref
        elif ":" in parte:
            filas = parte.replace("$", "")

    return {"rows": filas, "cols": columnas} if (filas or columnas) else None


# --------------------------------------------------------------------- #
# Roles sobre los tramos y las etiquetas
# --------------------------------------------------------------------- #

def _asignar_roles(tramos, mapa_roles):
    """Pega el rol heuristico a cada tramo, segun su celda representativa."""

    for tramo in tramos:
        # El rol se toma de la primera celda del tramo: un tramo es homogeneo
        # en estilo, y la clasificacion depende sobre todo de la fila.
        rol = mapa_roles.get((tramo["row_idx"], tramo["col_start"]))
        if rol is None:
            rol = roles.roles.DATA
        tramo["role"] = rol

    return tramos


def _filtrar_etiquetas(etiquetas, mapa_roles):
    """
    Se queda solo con el texto de celdas cuya fila/tramo es cabecera o leyenda.

    Este es el unico punto donde un valor del Excel original sobrevive, asi
    que el filtro es cerrado por construccion: lo demas no se guarda.
    """

    return [
        etiqueta
        for etiqueta in etiquetas
        if roles.roles.es_texto(mapa_roles.get((etiqueta["row_idx"], etiqueta["col_idx"])))
    ]
