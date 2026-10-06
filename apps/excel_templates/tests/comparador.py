"""
Comparacion celda por celda entre el Excel original y el exportado.

Es el criterio de aceptacion mas importante del modulo: dos archivos deben
coincidir en formato aunque el exportado no tenga datos. La comparacion
ignora los valores a proposito y se fija en lo que el usuario ve: fuente,
relleno, bordes, alineacion, formato numerico y proteccion.

Se comparan tambien las cosas de hoja (nombre, orden, anchos, altos, color de
pestana, zoom, paneles, autofiltro y formato condicional), porque un formato
correcto con la hoja desordenada sigue siendo una plantilla inservible.
"""

from ..colors import a_rgb_aproximado, desde_openpyxl
from ..styles import (
    alineacion_a_dict,
    borde_a_dict,
    dict_a_borde,
    fuente_a_dict,
    proteccion_a_dict,
    relleno_a_dict,
)


def firma_de_celda(celda):
    """
    Devuelve el formato de una celda como tupla comparable.

    Los colores se comparan por su forma original (`theme`+`tint`, `rgb`,
    `indexed`) y no por RGB resuelto: una plantilla que convierte un color de
    tema a RGB se ve casi igual, pero deja de responder al tema y por eso es
    una diferencia real.
    """

    fuente = fuente_a_dict(celda.font)
    relleno = relleno_a_dict(celda.fill)
    borde = borde_a_dict(celda.border)
    alineacion = alineacion_a_dict(celda.alignment)
    proteccion = proteccion_a_dict(celda.protection)

    return {
        "font": {
            "name": fuente["name"],
            "sz": fuente["sz"],
            "b": fuente["b"],
            "i": fuente["i"],
            "u": fuente["u"],
            "strike": fuente["strike"],
            "color": fuente["color"],
            "vertAlign": fuente["vertAlign"],
            "family": fuente["family"],
            "scheme": fuente["scheme"],
        },
        "fill": {
            "patternType": relleno.get("patternType"),
            "fgColor": relleno.get("fgColor"),
            "bgColor": relleno.get("bgColor"),
        },
        "border": borde,
        "alignment": alineacion,
        "protection": proteccion,
        "number_format": str(celda.number_format),
    }


def diferencias_de_firma(original, exportado):
    """Lista de diferencias entre dos firmas, campo por campo."""

    diferencias = []

    for seccion in ("font", "fill", "border", "alignment", "protection", "number_format"):
        a = original.get(seccion)
        b = exportado.get(seccion)

        if isinstance(a, dict):
            for clave in a:
                if a.get(clave) != (b or {}).get(clave):
                    diferencias.append(
                        f"{seccion}.{clave}: {a.get(clase)!r} != {(b or {}).get(clave)!r}"
                    )
        elif a != b:
            diferencias.append(f"{seccion}: {a!r} != {b!r}")

    return diferencias


def comparar_hojas(libro_original, libro_exportado, ignorar_valores=True):
    """
    Compara dos libros completos y devuelve la lista de diferencias.

    Devuelve una lista de strings legibles. Vacia significa formato identico.
    """

    diferencias = []

    nombres_original = list(libro_original.sheetnames)
    nombres_exportado = list(libro_exportado.sheetnames)

    if nombres_original != nombres_exportado:
        diferencias.append(
            f"nombres y orden de hojas: {nombres_original} != {nombres_exportado}"
        )
        return diferencias

    for nombre in nombres_original:
        diferencias.extend(
            _comparar_hoja(
                libro_original[nombre],
                libro_exportado[nombre],
                nombre,
                ignorar_valores,
            )
        )

    return diferencias


def _comparar_hoja(original, exportado, nombre, ignorar_valores):
    diferencias = []

    # -- celdas con estilo ------------------------------------------ #
    indices = _indices_relevantes(original, exportado)

    for fila, columna in sorted(indices):
        celda_original = original.cell(row=fila, column=columna)
        celda_exportado = exportado.cell(row=fila, column=columna)

        firma_original = firma_de_celda(celda_original)
        firma_exportado = firma_de_celda(celda_exportado)

        for diferencia in diferencias_de_firma(firma_original, firma_exportado):
            diferencias.append(
                f"{nombre}!{celda_original.coordinate}: {diferencia}"
            )

        if not ignorar_valores:
            if celda_original.value != celda_exportado.value:
                diferencias.append(
                    f"{nombre}!{celda_original.coordinate}: valor "
                    f"{celda_original.value!r} != {celda_exportado.value!r}"
                )

    # -- columnas ---------------------------------------------------- #
    diferencias.extend(_comparar_columnas(original, exportado, nombre))

    # -- filas ------------------------------------------------------- #
    diferencias.extend(_comparar_filas(original, exportado, nombre))

    # -- dimensiones de hoja ---------------------------------------- #
    if original.sheet_format.defaultRowHeight != exportado.sheet_format.defaultRowHeight:
        diferencias.append(
            f"{nombre}: alto de fila por defecto "
            f"{original.sheet_format.defaultRowHeight} != "
            f"{exportado.sheet_format.defaultRowHeight}"
        )

    if original.sheet_format.defaultColWidth != exportado.sheet_format.defaultColWidth:
        diferencias.append(
            f"{nombre}: ancho de columna por defecto "
            f"{original.sheet_format.defaultColWidth} != "
            f"{exportado.sheet_format.defaultColWidth}"
        )

    # -- color de pestana -------------------------------------------- #
    color_original = _color_pestana(original)
    color_exportado = _color_pestana(exportado)
    if color_original != color_exportado:
        diferencias.append(
            f"{nombre}: color de pestana {color_original!r} != {color_exportado!r}"
        )

    # -- vista: zoom, cuadricula, panel ------------------------------ #
    if original.sheet_view.showGridLines != exportado.sheet_view.showGridLines:
        diferencias.append(
            f"{nombre}: showGridLines "
            f"{original.sheet_view.showGridLines} != {exportado.sheet_view.showGridLines}"
        )

    zoom_original = getattr(original.sheet_view, "zoomScale", None)
    zoom_exportado = getattr(exportado.sheet_view, "zoomScale", None)
    if zoom_original != zoom_exportado:
        diferencias.append(f"{nombre}: zoom {zoom_original} != {zoom_exportado}")

    panel_original = _panel(original)
    panel_exportado = _panel(exportado)
    if panel_original != panel_exportado:
        diferencias.append(f"{nombre}: panel {panel_original} != {panel_exportado}")

    # -- combinaciones ----------------------------------------------- #
    combinaciones_original = sorted(str(r) for r in original.merged_cells.ranges)
    combinaciones_exportado = sorted(str(r) for r in exportado.merged_cells.ranges)
    if combinaciones_original != combinaciones_exportado:
        diferencias.append(
            f"{nombre}: celdas combinadas "
            f"{combinaciones_original} != {combinaciones_exportado}"
        )

    # -- autofiltro -------------------------------------------------- #
    diferencias.extend(_comparar_autofiltro(original, exportado, nombre))

    # -- formato condicional ----------------------------------------- #
    diferencias.extend(_comparar_condicionales(original, exportado, nombre))

    # -- validaciones de datos --------------------------------------- #
    diferencias.extend(_comparar_validaciones(original, exportado, nombre))

    # -- impresion --------------------------------------------------- #
    diferencias.extend(_comparar_impresion(original, exportado, nombre))

    return diferencias


def _indices_relevantes(original, exportado):
    """
    Celdas que hay que comparar: las que tienen estilo en cualquiera de los dos.

    Se recorren las filas escritas, no `max_row`: una hoja puede declarar un
    rango de un millon de filas sin tenerlas todas, y comparar eso entero seria
    slow sin encontrar nada.
    """

    indices = set()

    for libro in (original, exportado):
        for fila in libro.iter_rows():
            for celda in fila:
                if _tiene_estilo(celda):
                    indices.add((celda.row, celda.column))

    return indices


def _tiene_estilo(celda):
    """True si la celda lleva un formato explicito (no el estilo 0)."""

    estilo = getattr(celda, "_style", None)
    if estilo is None:
        return False
    try:
        return any(estilo)
    except TypeError:
        return False


def _comparar_columnas(original, exportado, nombre):
    diferencias = []

    letras_original = _indices_de_columna(original)
    letras_exportado = _indices_de_columna(exportado)

    for indice in sorted(set(letras_original) | set(letras_exportado)):
        dim_original = original.column_dimensions.get(_letra(indice))
        dim_exportado = exportado.column_dimensions.get(_letra(indice))

        ancho_original = dim_original.width if dim_original else None
        ancho_exportado = dim_exportado.width if dim_exportado else None

        if not _aproximado(ancho_original, ancho_exportado):
            diferencias.append(
                f"{nombre}: ancho columna {_letra(indice)} {ancho_original} != "
                f"{ancho_exportado}"
            )

        oculto_original = bool(dim_original.hidden) if dim_original else False
        oculto_exportado = bool(dim_exportado.hidden) if dim_exportado else False
        if oculto_original != oculto_exportado:
            diferencias.append(
                f"{nombre}: columna {_letra(indice)} oculta "
                f"{oculto_original} != {oculto_exportado}"
            )

    return diferencias


def _indices_de_columna(hoja):
    """Indices (base 1) de las columnas con dimensiones propias."""

    indices = set()
    for letra, dimension in hoja.column_dimensions.items():
        if dimension.min and dimension.max:
            indices.add(dimension.min)
            # Un rango `A:C` se expande para poder comparar columna por columna.
            if dimension.max - dimension.min > 32:
                indices.add(dimension.max)
            else:
                indices.update(range(dimension.min, dimension.max + 1))
    return indices


def _letra(indice):
    from openpyxl.utils import get_column_letter

    return get_column_letter(indice)


def _aproximado(a, b, tolerancia=0.02):
    """
    Compara flotantes con tolerancia.

    Excel guarda los anchos con varios decimales y openpyxl los reescribe
    redondeados. Una diferencia de 0,01 no se ve en pantalla ni al imprimir,
    asi que se tolera; una de 1 si.
    """

    if a is None or b is None:
        return a == b

    return abs(float(a) - float(b)) <= tolerancia


def _comparar_filas(original, exportado, nombre):
    diferencias = []

    indices_original = set(original.row_dimensions)
    indices_exportado = set(exportado.row_dimensions)

    for indice in sorted(indices_original | indices_exportado):
        dim_original = original.row_dimensions.get(indice)
        dim_exportado = exportado.row_dimensions.get(indice)

        alto_original = dim_original.height if dim_original else None
        alto_exportado = dim_exportado.height if dim_exportado else None

        if not _aproximado(alto_original, alto_exportado):
            diferencias.append(
                f"{nombre}: alto fila {indice} {alto_original} != {alto_exportado}"
            )

        oculto_original = bool(dim_original.hidden) if dim_original else False
        oculto_exportado = bool(dim_exportado.hidden) if dim_exportado else False
        if oculto_original != oculto_exportado:
            diferencias.append(
                f"{nombre}: fila {indice} oculta {oculto_original} != {oculto_exportado}"
            )

    return diferencias


def _color_pestana(hoja):
    color = hoja.sheet_properties.tabColor
    if color is None:
        return None
    return desde_openpyxl(color)


def _panel(hoja):
    pane = hoja.sheet_view.pane
    if pane is None:
        return None

    return {
        "xSplit": pane.xSplit,
        "ySplit": pane.ySplit,
        "topLeftCell": pane.topLeftCell,
        "activePane": pane.activePane,
        "state": pane.state,
    }


def _comparar_autofiltro(original, exportado, nombre):
    diferencias = []

    if original.auto_filter.ref != exportado.auto_filter.ref:
        diferencias.append(
            f"{nombre}: autofiltro ref {original.auto_filter.ref} != "
            f"{exportado.auto_filter.ref}"
        )

    filtros_original = original.auto_filter.filterColumn
    filtros_exportado = exportado.auto_filter.filterColumn

    if len(filtros_original) != len(filtros_exportado):
        diferencias.append(
            f"{nombre}: cantidad de columnas filtradas {len(filtros_original)} != "
            f"{len(filtros_exportado)}"
        )
        return diferencias

    for indice, (a, b) in enumerate(zip(filtros_original, filtros_exportado)):
        if a.colId != b.colId:
            diferencias.append(
                f"{nombre}: filtro columna {indice} colId {a.colId} != {b.colId}"
            )

        # Los valores del filtro: es lo que hace que la plantilla salga con la
        # vista ya filtrada.
        vacios_original = _valores_de_filtro(a)
        vacios_exportado = _valores_de_filtro(b)

        if vacios_original != vacios_exportado:
            diferencias.append(
                f"{nombre}: valores del filtro columna {indice} "
                f"{vacios_original} != {vacios_exportado}"
            )

    return diferencias


def _valores_de_filtro(columna):
    if columna.filters is None:
        return None

    # `Filters.filter` es una secuencia de cadenas, no de objetos con `.val`.
    # Ademas cubre el filtro de "sin coincidencias", que no usa lista de
    # valores sino el atributo `blank`.
    valores = list(columna.filters.filter)
    if columna.filters.blank:
        valores.append("<BLANK>")
    return valores


def _comparar_condicionales(original, exportado, nombre):
    diferencias = []

    reglas_original = _reglas_condicionales(original)
    reglas_exportado = _reglas_condicionales(exportado)

    rangos_original = sorted(reglas_original)
    rangos_exportado = sorted(reglas_exportado)

    if rangos_original != rangos_exportado:
        diferencias.append(
            f"{nombre}: rangos de formato condicional "
            f"{rangos_original} != {rangos_exportado}"
        )
        return diferencias

    for rango in rangos_original:
        for a, b in zip(reglas_original[rango], reglas_exportado[rango]):
            if a.get("type") != b.get("type"):
                diferencias.append(
                    f"{nombre}!{rango}: tipo de regla {a.get('type')} != {b.get('type')}"
                )
            if a.get("operator") != b.get("operator"):
                diferencias.append(
                    f"{nombre}!{rango}: operador {a.get('operator')} != "
                    f"{b.get('operator')}"
                )
            if a.get("priority") != b.get("priority"):
                diferencias.append(
                    f"{nombre}!{rango}: prioridad {a.get('priority')} != "
                    f"{b.get('priority')}"
                )
            if a.get("formula") != b.get("formula"):
                diferencias.append(
                    f"{nombre}!{rango}: formula {a.get('formula')} != {b.get('formula')}"
                )
            if _firma_dxf(a) != _firma_dxf(b):
                diferencias.append(
                    f"{nombre}!{rango}: estilo diferencial {_firma_dxf(a)} != "
                    f"{_firma_dxf(b)}"
                )

    return diferencias


def _reglas_condicionales(hoja):
    """Reglas por rango, en dicts comparables."""

    resultado = {}

    for rango in hoja.conditional_formatting:
        reglas = []
        for regla in hoja.conditional_formatting[rango]:
            dxf = getattr(regla, "dxf", None)
            reglas.append(
                {
                    "type": regla.type,
                    "operator": regla.operator,
                    "priority": regla.priority,
                    "formula": list(regla.formula) if regla.formula else None,
                    "dxf": _firma_dxf(regla),
                }
            )
        resultado[str(rango.sqref)] = reglas

    return resultado


def _firma_dxf(regla):
    """El estilo diferencial de una regla, como tupla comparable."""

    dxf = getattr(regla, "dxf", None)
    if dxf is None:
        return None

    partes = []

    if dxf.font is not None:
        partes.append(("font", _fuente_simple(dxf.font)))

    if dxf.fill is not None:
        partes.append(("fill", _relleno_simple(dxf.fill)))

    if dxf.border is not None:
        partes.append(("border", _borde_simple(dxf.border)))

    if dxf.alignment is not None:
        partes.append(("alignment", tuple(sorted(alineacion_a_dict(dxf.alignment).items()))))

    if dxf.numFmt is not None:
        partes.append(("numFmt", getattr(dxf.numFmt, "formatCode", None)))

    return tuple(partes)


def _fuente_simple(fuente):
    """Fuente en forma estable, con el color sin resolver a RGB."""

    return (
        bool(fuente.b),
        bool(fuente.i),
        repr(desde_openpyxl(fuente.color)),
        fuente.name,
    )


def _relleno_simple(relleno):
    return (
        relleno.patternType,
        repr(desde_openpyxl(relleno.fgColor)),
    )


def _borde_simple(borde):
    lados = []
    for lado in ("left", "right", "top", "bottom"):
        parte = getattr(borde, lado, None)
        if parte is None or parte.style is None:
            lados.append(None)
        else:
            lados.append((parte.style, repr(desde_openpyxl(parte.color))))
    return tuple(lados)


def _comparar_validaciones(original, exportado, nombre):
    diferencias = []

    validaciones_original = list(original.data_validations.dataValidation)
    validaciones_exportado = list(exportado.data_validations.dataValidation)

    def _firma(validaciones):
        return sorted(
            (
                str(v.sqref),
                v.type,
                v.formula1,
                v.operator,
            )
            for v in validaciones
        )

    if _firma(validaciones_original) != _firma(validaciones_exportado):
        diferencias.append(
            f"{nombre}: validaciones {_firma(validaciones_original)} != "
            f"{_firma(validaciones_exportado)}"
        )

    return diferencias


def _comparar_impresion(original, exportado, nombre):
    diferencias = []

    if original.page_setup.orientation != exportado.page_setup.orientation:
        diferencias.append(
            f"{nombre}: orientacion {original.page_setup.orientation} != "
            f"{exportado.page_setup.orientation}"
        )

    if original.page_setup.paperSize != exportado.page_setup.paperSize:
        diferencias.append(
            f"{nombre}: papel {original.page_setup.paperSize} != "
            f"{exportado.page_setup.paperSize}"
        )

    if bool(original.page_setup.fitToPage) != bool(exportado.page_setup.fitToPage):
        diferencias.append(
            f"{nombre}: fitToPage {original.page_setup.fitToPage} != "
            f"{exportado.page_setup.fitToPage}"
        )

    for campo in ("left", "right", "top", "bottom", "header", "footer"):
        a = getattr(original.page_margins, campo)
        b = getattr(exportado.page_margins, campo)
        if not _aproximado(a, b, tolerancia=0.001):
            diferencias.append(f"{nombre}: margen {campo} {a} != {b}")

    return diferencias


# Reexportado para los tests que comparen colores aproximados.
__all__ = [
    "comparar_hojas",
    "diferencias_de_firma",
    "firma_de_celda",
    "a_rgb_aproximado",
    "dict_a_borde",
]