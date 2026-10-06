"""
Render: modelo intermedio -> `.xlsx`/`.xlsm` vacio de datos.

Aplica formato y descarta contenido segun `ExportOptions`. El orden importa:
primero se reconstruye la estructura (hojas, columnas, filas), despues los
tramos de estilo, y al final lo que depende de todo lo anterior (inmovilizado,
filtro, formato condicional, impresion).

`prototype` reduce el numero de filas replicadas para archivos grandes; el
formato de las filas que no se replican queda summarized en una fila tipo, y el
resto de filas conserva solo el estilo de columna. Es una degradacion
deliberada que el reporte declara.
"""

import io
from copy import copy

from .colors import a_openpyxl
from .hashing import hash_de
from .options import ExportOptions
from .report import Reporte
from .styles import RegistroEstilos


def renderizar(modelo, opciones=None, destino=None):
    """
    Genera el `.xlsx` en memoria (o lo escribe en `destino`).

    Devuelve los bytes del archivo siempre, para que el llamador elija entre
    guardarlos en disco o mandarlos en la respuesta HTTP.
    """

    import openpyxl

    opciones = (opciones or ExportOptions()).normalized()
    reporte = Reporte()

    registro = RegistroEstilos()
    # Se llenan con las piezas de la base para que `componer` encuentre todo.
    registro.fuentes = dict(modelo["estilos"]["fonts"])
    registro.rellenos = dict(modelo["estilos"]["fills"])
    registro.bordes = dict(modelo["estilos"]["borders"])
    registro.alineaciones = dict(modelo["estilos"]["alignments"])
    registro.protecciones = dict(modelo["estilos"]["protections"])
    registro.formatos = dict(modelo["estilos"]["number_formats"])
    registro.estilos = dict(modelo["estilos"]["styles"])

    libro = openpyxl.Workbook()
    # El libro nuevo nace con una hoja llamada "Sheet": se quita de inmediato
    # para no heredar un nombre que no estaba en el original.
    libro.remove(libro.active)

    dxfs = _dxfs_por_hash(modelo.get("dxfs", []), reporte)

    for hoja in modelo["hojas"]:
        _crear_hoja(libro, hoja, registro, dxfs, opciones, reporte)

    _aplicar_nombres_definidos(libro, modelo, reporte)

    buffer = io.BytesIO()
    # Un libro sin hojas no se puede guardar; si el original no tenia ninguna,
    # se deja una hoja vacia para que el archivo sea valido.
    if not libro.sheetnames:
        libro.create_sheet("Hoja1")

    libro.save(buffer)
    datos = buffer.getvalue()

    # openpyxl escribe su propio theme y su propia lista de estilos. Como los
    # colores se guardan como `theme=N` en vez de resueltos a RGB, sustituir el
    # theme por el del original es lo unico que hace que esos colores apunten a
    # la misma paleta. Se hace despues de guardar porque el theme es una parte
    # mas del ZIP.
    tema = (modelo.get("workbook") or {}).get("theme_xml")
    if tema:
        datos = _reemplazar_parte(datos, "xl/theme/theme1.xml", tema, reporte)

    if destino:
        with open(destino, "wb") as archivo:
            archivo.write(datos)

    return datos, reporte


def _reemplazar_parte(datos, nombre, contenido, reporte):
    """
    Sustituye una parte del `.xlsx` manteniendo el resto del ZIP intacto.

    Va por el ZIP y no por openpyxl porque el theme es XML crudo que
    openpyxl no modela: no hay forma de asignarlo al libro. Se reconstruye el
    archivo entero porque `zipfile` no permite reemplazar una entrada.

    Si la parte no existe en el ZIP, se anade junto con su relacion: si el
    original tenia theme (y lo tenia, para eso se guardo), el archivo nuevo
    tambien deberia tenerlo, pero si openpyxl decidio no escribirlo hay que
    crear la relacion o Excel ignoraria el theme.
    """

    import zipfile

    origen = io.BytesIO(datos)
    salida = io.BytesIO()

    with zipfile.ZipFile(origen, "r") as paquete:
        entradas = [(info, paquete.read(info.filename)) for info in paquete.infolist()]

    nombres = {info.filename for info, _ in entradas}

    if nombre not in nombres:
        reporte.degradado(
            "theme",
            f"el archivo generado no trae '{nombre}' y no se puede anadir sin "
            "su relacion en el paquete; se deja el theme por defecto",
        )
        return datos

    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as paquete:
        for info, contenido_actual in entradas:
            if info.filename == nombre:
                info = zipfile.ZipInfo(nombre, date_time=info.date_time)
                info.compress_type = zipfile.ZIP_DEFLATED
                paquete.writestr(info, contenido)
            else:
                paquete.writestr(info, contenido_actual)

    return salida.getvalue()


# --------------------------------------------------------------------- #
# Hoja
# --------------------------------------------------------------------- #

def _crear_hoja(libro, hoja, registro, dxfs, opciones, reporte):
    """Construye una hoja completa a partir de su registro en la base."""

    nombre = hoja["name"]

    ws = libro.create_sheet(title=nombre)

    if not opciones.keep_sheet_state and hoja.get("state") != "VISIBLE":
        ws.sheet_state = "visible"

    _aplicar_vista(ws, hoja.get("sheet_view_json"), opciones)
    _aplicar_pestana(ws, hoja.get("tab_color_json"))
    _aplicar_formatos_por_defecto(ws, hoja)

    # Las columnas van primero: el estilo de columna es el que se aplica a las
    # celdas vacias, y hay que fijarlo antes de escribir los tramos.
    _aplicar_columnas(ws, hoja.get("columns", []), registro)

    filas_por_indice = _aplicar_filas(
        ws, hoja.get("rows", []), hoja.get("style_runs", []), registro, opciones, reporte
    )

    _aplicar_texto_etiquetas(ws, hoja.get("labels", []), opciones)

    _aplicar_combinaciones(ws, hoja.get("merged", []))
    _aplicar_validaciones(ws, hoja.get("data_validations", []), opciones)
    _aplicar_condicionales(ws, hoja.get("conditional_formats", []), registro, dxfs, reporte)
    _aplicar_autofiltro(ws, hoja.get("autofilter"), opciones, reporte)
    _aplicar_tablas(ws, hoja.get("tables", []), reporte)
    _aplicar_comentarios(ws, hoja.get("comments", []), opciones)
    _aplicar_impresion(ws, hoja, reporte)

    del filas_por_indice

    return ws


def _aplicar_vista(ws, vista, opciones):
    """
    `sheetView`: zoom, lineas de cuadricula, panel inmovilizado, seleccion.

    El panel se reconstruye desde `pane`, no desde `freeze_panes`, porque
    `freeze_panes` de openpyxl solo cubre el caso tipico y el ejemplo tiene
    paneles con `xSplit`/`ySplit` atipicos.
    """

    if not vista:
        return

    vista_limpia = {k: v for k, v in vista.items() if not k.startswith("__")}

    if "showGridLines" in vista_limpia:
        ws.sheet_view.showGridLines = bool(vista_limpia["showGridLines"])

    if "showRowColHeaders" in vista_limpia:
        ws.sheet_view.showRowColHeaders = bool(vista_limpia["showRowColHeaders"])

    if "zoomScale" in vista_limpia:
        ws.sheet_view.zoomScale = vista_limpia["zoomScale"]

    if "rightToLeft" in vista_limpia:
        ws.sheet_view.rightToLeft = bool(vista_limpia["rightToLeft"])

    panel = vista_limpia.get("pane")
    if panel:
        _aplicar_panel(ws, panel, reporte=None)


def _aplicar_panel(ws, panel, reporte):
    """
    Panel inmovilizado desde sus atributos literales.

    Se escribe directamente en `ws.sheet_view.pane` porque la API de
    openpyxl para paneles es incompleta: `xSplit` e `ySplit` con valores
    atipicos (por ejemplo 417) se pierden por `freeze_panes`.
    """

    from openpyxl.worksheet.views import Pane

    atributos = {
        "xSplit": panel.get("xSplit"),
        "ySplit": panel.get("ySplit"),
        "topLeftCell": panel.get("topLeftCell"),
        "activePane": panel.get("activePane"),
        "state": panel.get("state"),
    }

    # openpyxl quiere numeros, no strings.
    for clave in ("xSplit", "ySplit"):
        if atributos[clave] is not None:
            try:
                atributos[clave] = float(atributos[clave])
            except (TypeError, ValueError):
                del atributos[clave]

    # Un panel sin ningun split no es un panel: se descarta.
    if not any(atributos.get(clave) for clave in ("xSplit", "ySplit")):
        if reporte is not None:
            reporte.degradado(
                "freeze_view", f"panel sin xSplit/ySplit, no se aplica: {panel}"
            )
        return

    ws.sheet_view.pane = Pane(**atributos)


def _aplicar_pestana(ws, color):
    """Color de la pestana de la hoja."""

    if not color:
        return

    ws.sheet_properties.tabColor = a_openpyxl(color)


def _aplicar_formatos_por_defecto(ws, hoja):
    """
    Alto y ancho por defecto de la hoja.

    Sin esto, una hoja con alto de fila 12,75 (un cuarto de pulgada) sale con
    el alto estandar de Excel y todas las filas se ven mas altas de lo que
    deberian.
    """

    formato = ws.sheet_format

    if hoja.get("default_row_height") is not None:
        formato.defaultRowHeight = hoja["default_row_height"]

    if hoja.get("default_col_width") is not None:
        formato.defaultColWidth = hoja["default_col_width"]


def _aplicar_columnas(ws, columnas, registro):
    """Anchos, ocultamiento, agrupamiento y estilo por defecto de columna."""

    from openpyxl.utils import get_column_letter

    for columna in columnas:
        letra_inicio = get_column_letter(columna["min_idx"])
        letra_fin = get_column_letter(columna["max_idx"])
        clave = letra_inicio if letra_inicio == letra_fin else f"{letra_inicio}:{letra_fin}"

        dimensiones = ws.column_dimensions[clave]
        dimensiones.min = columna["min_idx"]
        dimensiones.max = columna["max_idx"]

        if columna.get("width") is not None:
            dimensiones.width = columna["width"]

        if columna.get("hidden"):
            dimensiones.hidden = True

        if columna.get("best_fit"):
            dimensiones.bestFit = True

        if columna.get("outline_level"):
            dimensiones.outlineLevel = columna["outline_level"]

        if columna.get("style"):
            # En openpyxl 3.1 `Dimension.style` es un alias de `style_id`, que
            # solo tiene getter. El StyleArray interno si se puede asignar y
            # termina serializando el estilo de la columna correctamente.
            dimensiones._style = copy(
                _estilo_named(ws.parent, registro, columna["style"])
            )


def _estilo_named(libro, registro, hash_estilo):
    """
    Registra un estilo en la paleta del libro y devuelve su `StyleArray`.

    El estilo de columna y el de fila se referencian por indice en el XML, y
    openpyxl no expone una forma limpia de crear uno. Se anade un `NamedStyle`
    con un nombre derivado del hash (determinista). Las dimensiones de
    fila/columna no permiten asignar su propiedad `style`, pero si aceptan el
    array interno. Si dos dimensiones comparten estilo, reutilizan la entrada.
    """

    from openpyxl.styles import NamedStyle

    nombre = f"xt_{hash_estilo[:16]}"

    if nombre in libro.named_styles:
        return next(
            estilo._style
            for estilo in libro._named_styles
            if estilo.name == nombre
        )

    fuente, relleno, borde, alineacion, proteccion, numero = registro.componer(hash_estilo)

    estilo = NamedStyle(name=nombre)
    estilo.font = fuente
    estilo.fill = relleno
    estilo.border = borde
    if alineacion is not None:
        estilo.alignment = alineacion
    if proteccion is not None:
        estilo.protection = proteccion
    estilo.number_format = numero

    libro.add_named_style(estilo)
    return estilo._style


def _aplicar_filas(ws, filas, tramos, registro, opciones, reporte):
    """
    Alturas, ocultamiento y estilo por tramo.

    Los tramos se agrupan por fila para no repetir el acceso al diccionario de
    estilos por celda: en un archivo grande hay decenas de miles de tramos y
    cada `ws.cell()` es una creacion de objeto.
    """

    for fila in filas:
        indice = fila["row_idx"]
        dimension = ws.row_dimensions[indice]

        if fila.get("height") is not None:
            dimension.height = fila["height"]

        if fila.get("hidden") and opciones.keep_hidden_rows:
            dimension.hidden = True

        if fila.get("outline_level"):
            dimension.outlineLevel = fila["outline_level"]

    # Estilo por defecto de fila (`<row s="n">`): se aplica a las celdas sin
    # tramo propio. Se hace antes de los tramos para que estos la pisen.
    for fila in filas:
        if fila.get("style"):
            ws.row_dimensions[fila["row_idx"]]._style = copy(
                _estilo_named(ws.parent, registro, fila["style"])
            )

    tramos_por_fila = {}
    for tramo in tramos:
        tramos_por_fila.setdefault(tramo["row_idx"], []).append(tramo)

    for indice_fila, lista in tramos_por_fila.items():
        for tramo in lista:
            fuente, relleno, borde, alineacion, proteccion, numero = registro.componer(
                tramo["style"]
            )
            _pintar_tramo(
                ws, indice_fila, tramo["col_start"], tramo["col_end"],
                fuente, relleno, borde, alineacion, proteccion, numero,
            )

    return tramos_por_fila


def _pintar_tramo(ws, fila, col_inicio, col_fin, fuente, relleno, borde,
                  alineacion, proteccion, numero):
    """
    Aplica un estilo a un tramo de celdas contiguas.

    Se asignan los componentes uno por uno en vez de un `Style` completo porque
    openpyxl no tiene un `apply_style` en lote: `ws.cell(fila, col)` crea la
    celda si no existe y ahi se le pone el formato. Las celdas quedan vacias,
    que es justo lo que se busca en una plantilla.
    """

    for columna in range(col_inicio, col_fin + 1):
        celda = ws.cell(row=fila, column=columna)
        celda.font = fuente
        celda.fill = relleno
        celda.border = borde
        if alineacion is not None:
            celda.alignment = alineacion
        if proteccion is not None:
            celda.protection = proteccion
        celda.number_format = numero


def _aplicar_texto_etiquetas(ws, etiquetas, opciones):
    """
    Escribe el texto conservado (cabeceras y leyendas).

    Las etiquetas solo existen para celdas cuyo rol conserva texto, asi que si
    `keep_labels` es False no se escribe ninguna y la plantilla sale sin
    cabeceras, que es justo lo que esa opcion pide.
    """

    if not opciones.keep_labels:
        return

    for etiqueta in etiquetas:
        ws.cell(
            row=etiqueta["row_idx"],
            column=etiqueta["col_idx"],
        ).value = etiqueta["value"]


# --------------------------------------------------------------------- #
# Estructura
# --------------------------------------------------------------------- #

def _aplicar_combinaciones(ws, combinaciones):
    """Rangos combinados, en el orden original."""

    for combinacion in combinaciones:
        ws.merge_cells(combinacion["ref"])


def _aplicar_validaciones(ws, validaciones, opciones):
    """
    Validaciones de datos.

    `keep_data_validation_lists` decide si se reconstruyen. Una lista
    desplegable es contenido (una lista de estados, por ejemplo) pero tambien
    es parte de como se llena la plantilla, asi que por defecto se conserva.
    """

    if not opciones.keep_data_validation_lists:
        return

    from openpyxl.worksheet.datavalidation import DataValidation

    for validacion in validaciones:
        opciones_dv = validacion.get("options_json") or {}
        tipo = validacion.get("type") or "list"

        # Una lista literal se reconstruye con sus valores; una que apunta a un
        # rango se deja como formula.
        valores = opciones_dv.get("valores")
        formula1 = validacion.get("formula1_json")

        if valores is not None:
            formula1 = '"' + ",".join(valores) + '"'

        if not formula1:
            continue

        dv = DataValidation(
            type=tipo,
            formula1=formula1,
            formula2=validacion.get("formula2_json"),
            allow_blank=_bool(opciones_dv.get("allowBlank"), True),
            showErrorMessage=_bool(opciones_dv.get("showErrorMessage"), True),
            showInputMessage=_bool(opciones_dv.get("showInputMessage"), True),
            errorTitle=opciones_dv.get("errorTitle"),
            error=opciones_dv.get("error"),
            promptTitle=opciones_dv.get("promptTitle"),
            prompt=opciones_dv.get("prompt"),
        )

        for rango in validacion.get("sqref_json") or []:
            ws.add_data_validation(dv)
            dv.add(rango)


def _bool(valor, defecto=False):
    """Convierte los booleanos de Excel a bool."""

    if valor is None:
        return defecto
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ("1", "true", "on")


# --------------------------------------------------------------------- #
# Formato condicional
# --------------------------------------------------------------------- #

def _dxfs_por_hash(dxfs, reporte):
    """
    Crea objetos `DifferentialStyle` de openpyxl a partir de los dxf guardados.

    La clave del dict es el mismo `hash_de` que uso `persist` al guardar, para
    que la regla de formato condicional encuentre su dxf por hash sin
    ambiguedad. Se usa `hash_de` y no el `hash()` de Python porque este ultimo
    cambia entre procesos y el render puede correr en otro.

    Los dxf se guardaron leidos del XML crudo precisamente para no perder
    `theme`+`tint`. Si algo no se sabe reproducir, se avisa en el reporte en
    vez de escribir un estilo aproximado en silencio.
    """

    # `DifferentialStyle` no se exporta desde `openpyxl.styles`; vive en
    # `openpyxl.styles.differential`.
    from openpyxl.styles import Alignment, Protection
    from openpyxl.styles.differential import DifferentialStyle

    estilos = {}

    for dxf in dxfs or []:
        try:
            estilo = DifferentialStyle(
                font=_dxf_fuente(dxf.get("font")),
                fill=_dxf_relleno(dxf.get("fill")),
                border=_dxf_borde(dxf.get("border")),
                alignment=_dxf_alineacion(dxf.get("alignment")),
                numFmt=_numfmt(dxf.get("numFmt")),
                protection=_dxf_proteccion(dxf.get("protection")),
            )
            estilos[hash_de(dxf)] = estilo

        except (TypeError, ValueError) as error:
            reporte.degradado("conditional_format", f"dxf no reconstruible: {error}")

    return estilos


def _dxf_alineacion(alineacion):
    """`dxf/alignment` a `Alignment` de openpyxl."""

    from openpyxl.styles import Alignment

    if not alineacion:
        return None

    # Los atributos del XML y los de openpyxl no comparten nombre en todos los
    # casos, asi que se mapea de forma explicita.
    return Alignment(
        horizontal=alineacion.get("horizontal"),
        vertical=alineacion.get("vertical"),
        wrap_text=_bool(alineacion.get("wrapText"), False),
        indent=_int(alineacion.get("indent")) or 0,
        text_rotation=_int(alineacion.get("textRotation")) or 0,
        shrink_to_fit=_bool(alineacion.get("shrinkToFit"), False),
        readingOrder=_int(alineacion.get("readingOrder")) or 0,
        justifyLastLine=_bool(alineacion.get("justifyLastLine"), False),
    )


def _dxf_proteccion(proteccion):
    """`dxf/protection` a `Protection` de openpyxl."""

    from openpyxl.styles import Protection

    if not proteccion:
        return None

    return Protection(
        locked=_bool(proteccion.get("locked"), True),
        hidden=_bool(proteccion.get("hidden"), False),
    )


def _dxf_fuente(fuente):
    """`dxf/font` a `openpyxl.styles.Font`, o None."""

    from openpyxl.styles import Font

    if not fuente:
        return None

    kwargs = {}
    if fuente.get("name"):
        kwargs["name"] = fuente["name"]
    if fuente.get("sz"):
        kwargs["sz"] = float(fuente["sz"])
    if fuente.get("b"):
        kwargs["bold"] = True
    if fuente.get("i"):
        kwargs["italic"] = True
    if fuente.get("u"):
        kwargs["underline"] = fuente["u"]
    if fuente.get("strike"):
        kwargs["strike"] = True
    if fuente.get("color"):
        kwargs["color"] = a_openpyxl(fuente["color"])
    if fuente.get("vertAlign"):
        kwargs["vertAlign"] = fuente["vertAlign"]
    if fuente.get("family"):
        kwargs["family"] = str(fuente["family"])
    if fuente.get("scheme"):
        kwargs["scheme"] = fuente["scheme"]
    return Font(**kwargs)


def _dxf_relleno(relleno):
    """`dxf/fill` a `PatternFill`."""

    from openpyxl.styles import PatternFill

    if not relleno or relleno.get("kind") != "pattern":
        return None

    kwargs = {"patternType": relleno.get("patternType")}

    # openpyxl no acepta `fgColor=None`: el descriptor espera un `Color` y
    # revienta con un TypeError. Un dxf puede traer solo uno de los dos
    # colores, asi que se pasan solo los que existen.
    for nombre in ("fgColor", "bgColor"):
        color = a_openpyxl(relleno.get(nombre))
        if color is not None:
            kwargs[nombre] = color

    return PatternFill(**kwargs)


def _dxf_borde(borde):
    """`dxf/border` a `Border`, con los cuatro lados."""

    from openpyxl.styles import Border, Side

    if not borde:
        return None

    lados = {}
    for lado in ("left", "right", "top", "bottom"):
        datos = borde.get(lado)
        if not datos:
            lados[lado] = Side()
            continue
        lados[lado] = Side(
            style=datos.get("style"),
            color=a_openpyxl(datos.get("color")),
        )

    return Border(**lados)


def _numfmt(numfmt):
    """`dxf/numFmt` a un `NumberFormat` de openpyxl."""

    from openpyxl.styles.numbers import NumberFormat

    codigo = (numfmt or {}).get("formatCode")
    if not codigo:
        return None

    return NumberFormat(
        numFmtId=int(numfmt.get("numFmtId") or 0),
        formatCode=codigo,
    )


def _aplicar_condicionales(ws, condicionales, registro, dxfs, reporte):
    """
    Reglas de formato condicional.

    El `sqref` se pasa tal cual, con todos sus fragmentos: normalizarlo a un
    unico rango cambiaria que celdas se resaltaban.

    Las reglas se construyen con `Rule`, que acepta un `dxf` ya hecho y todos
    los atributos tal cual. Los atajos de openpyxl (`CellIsRule`,
    `ColorScaleRule`, ...) reciben `font`/`fill`/`border` sueltos y montan el
    dxf por dentro, asi que no admiten un dxf leido del XML; ademas
    `colorScale` y `iconSet` admiten un numero fijo de colores y umbrales, y
    reconstruirlos por ahi perderia los que traia el original.
    """

    from openpyxl.formatting.rule import (
        ColorScale,
        DataBar,
        FormatObject,
        IconSet,
        Rule,
    )

    for regla in condicionales:
        rangos = " ".join(regla.get("sqref_json") or [])
        if not rangos:
            continue

        tipo = regla.get("type")

        try:
            regla_opl = _regla_de_openpyxl(regla, dxfs)
        except (TypeError, ValueError) as error:
            reporte.degradado(
                "conditional_format",
                f"regla de tipo '{tipo}' no reconstruible: {error}",
                ws.title,
            )
            continue

        if regla_opl is None:
            continue

        # `Rule` no acepta `priority=None` con tipo `colorScale` y similares;
        # el rango se declara igualmente para que el usuario vea donde aplica.
        regla_opl.priority = regla.get("priority") or 1
        ws.conditional_formatting.add(rangos, regla_opl)


def _regla_de_openpyxl(regla, dxfs):
    """
    Una regla de la base a un objeto `Rule` de openpyxl, o None.

    None significa "no hay nada que escribir" (por ejemplo, una escala de
    color guardada sin colores): se avisa en el reporte desde el llamante.
    """

    from openpyxl.formatting.rule import Rule

    tipo = regla.get("type") or "expression"
    estilo_dxf = dxfs.get(regla.get("dxf")) if regla.get("dxf") else None

    escala = regla.get("color_scale_json")
    barra = regla.get("data_bar_json")
    iconos = regla.get("icon_set_json")

    if tipo == "colorScale":
        if not escala:
            return None
        return Rule(
            type=tipo,
            colorScale=ColorScale(
                cfvo=[_cfvo_de_openpyxl(c) for c in escala.get("cfvo") or []],
                color=[_color_de_regla(c) for c in escala.get("color") or []],
            ),
        )

    if tipo == "dataBar":
        if not barra:
            return None
        return Rule(
            type=tipo,
            dataBar=DataBar(
                cfvo=[_cfvo_de_openpyxl(c) for c in barra.get("cfvo") or []],
                color=[_color_de_regla(c) for c in barra.get("color") or []],
                showValue=_bool(barra.get("showValue"), True),
                minLength=_int(barra.get("minLength")) or 0,
                maxLength=_int(barra.get("maxLength")) or 100,
            ),
        )

    if tipo == "iconSet":
        if not iconos:
            return None
        return Rule(
            type=tipo,
            iconSet=IconSet(
                iconSet=iconos.get("iconSet") or "3TrafficLights1",
                cfvo=[_cfvo_de_openpyxl(c) for c in iconos.get("cfvo") or []],
                showValue=_bool(iconos.get("showValue"), True),
                reverse=_bool(iconos.get("reverse"), False),
            ),
        )

    # Reglas de celda, expresion y texto: el resto de atributos son todos
    # opcionales y openpyxl los escribe solo si vienen puestos, que es
    # exactamente lo que queremos.
    return Rule(
        type=tipo,
        dxf=estilo_dxf,
        operator=regla.get("operator") or None,
        formula=regla.get("formulas_json") or None,
        stopIfTrue=regla.get("stop_if_true") or None,
        text=regla.get("text") or None,
        timePeriod=regla.get("time_period") or None,
        rank=regla.get("rank"),
        percent=regla.get("percent"),
        bottom=regla.get("bottom"),
        stdDev=regla.get("std_dev"),
        aboveAverage=regla.get("above_average"),
        equalAverage=regla.get("equal_average"),
    )


def _color_de_regla(color):
    """Color de una escala/barra/iconos a `Color` de openpyxl."""

    from openpyxl.styles.colors import Color

    convertido = a_openpyxl(color)
    if convertido is not None:
        return convertido

    # Las barras de datos de Excel a veces traen `rgb` con 6 digitos en vez de
    # los 8 del formato aRGB. Se completa el alpha en vez de tirar la regla.
    if color and color.get("type") == "rgb" and color.get("value"):
        valor = str(color["value"])
        if len(valor) == 6:
            return Color(rgb="FF" + valor.upper())
        return Color(rgb=valor.upper())

    return Color()


def _cfvo_de_openpyxl(cfvo):
    """Un `<cfvo>` a `FormatObject` de openpyxl."""

    from openpyxl.formatting.rule import FormatObject

    tipo = (cfvo or {}).get("type") or "min"
    valor = (cfvo or {}).get("val")

    if valor is None:
        return FormatObject(type=tipo)
    if tipo in ("num", "percent"):
        return FormatObject(type=tipo, val=float(valor))
    return FormatObject(type=tipo, val=str(valor))


# --------------------------------------------------------------------- #
# Filtro automatico
# --------------------------------------------------------------------- #

def _aplicar_autofiltro(ws, autofiltro, opciones, reporte):
    """
    Autofiltro con su rango y sus criterios activos.

    Los criterios se reconstruyen tal cual, cada uno con su `colId` original.
    Un filtro que openpyxl no sabe reproducir no se inventa: se declara en el
    reporte, y el rango del autofiltro sigue puesto, que es lo que el usuario ve.
    """

    if not autofiltro or not autofiltro.get("ref"):
        return

    ws.auto_filter.ref = autofiltro["ref"]

    columnas = autofiltro.get("columns_json") or []

    for indice, columna in enumerate(columnas):
        # El `colId` del original manda: `enumerate` daria la posicion en la
        # lista, que solo coincide con el indice real de columna cuando el
        # archivo filtra desde la primera. Filtrar la columna equivocada deja
        # la plantilla con la vista mal puesta.
        col_id = _int(columna.get("colId"))
        if col_id is None:
            col_id = indice

        objeto = _columna_filtro_de_openpyxl(columna, col_id)

        if objeto is None:
            reporte.degradado(
                "autofilter",
                f"filtro de la columna {col_id} guardado pero no reexportado: "
                f"{sorted(columna)}",
                ws.title,
            )
            continue

        ws.auto_filter.filterColumn.append(objeto)


def _columna_filtro_de_openpyxl(columna, col_id):
    """
    Una entrada de `columns_json` a un `FilterColumn` de openpyxl.

    Se construye el objeto directamente en vez de usar `add_filter_column`
    porque ese atajo solo sabe escribir filtros por lista de valores y
    reinicia el `colId` segun la posicion en la lista. Devuelve None cuando el
    filtro es de un tipo que no se sabe reproducir (color, icono, dinamico o
    los 10 mas altos), para que el llamante lo declare en el reporte en vez de
    escribir un filtro que no es el del original.
    """

    from openpyxl.worksheet.filters import FilterColumn, Filters

    objeto = FilterColumn(colId=col_id)

    if columna.get("showButton") is not None:
        objeto.showButton = _bool(columna["showButton"], True)
    if columna.get("hiddenButton"):
        objeto.hiddenButton = _bool(columna["hiddenButton"], False)

    filtros = columna.get("filters")
    if filtros:
        objeto.filters = Filters(
            blank=_bool(filtros.get("blank"), False),
            filter=[str(v) for v in (filtros.get("vals") or [])],
        )
        return objeto

    personalizados = columna.get("customFilters")
    if personalizados:
        from openpyxl.worksheet.filters import CustomFilter, CustomFilters

        condiciones = [
            CustomFilter(
                operator=condicion.get("operator") or "equal",
                val=str(condicion.get("val") or ""),
            )
            for condicion in personalizados
        ]
        objeto.customFilters = CustomFilters(customFilter=condiciones)
        return objeto

    # Los filtros dinamicos, de color, de icono y de "10 mas altos" tambien
    # tienen representacion en openpyxl, pero su semantica depende de datos
    # vivos del libro: se guardan y se avisa, sin inventar una regla.
    if any(
        columna.get(clave)
        for clave in ("dynamicFilter", "colorFilter", "iconFilter", "top10")
    ):
        return None

    # Una columna sin ningun criterio activo no aporta nada: se omite en vez
    # de escribir un `<filterColumn>` vacio que Excel interpretaria como filtro
    # sin condiciones.
    return None


# --------------------------------------------------------------------- #
# Tablas
# --------------------------------------------------------------------- #

def _aplicar_tablas(ws, tablas, reporte):
    """
    Tablas de Excel (`<table>`).

    Se reconstruyen solo si el rango y el nombre son utilizables; si no, se
    declaran en el reporte en vez de crear una tabla a medias que Excel
    rechazaria al abrir el archivo.
    """

    if not tablas:
        return

    from openpyxl.worksheet.table import Table, TableStyleInfo

    for tabla in tablas:
        nombre = tabla.get("name")
        referencia = tabla.get("ref")

        if not nombre or not referencia:
            reporte.degradado(
                "tables",
                f"tabla sin nombre o sin rango, no reexportada: {tabla}",
                ws.title,
            )
            continue

        contenido = tabla.get("table_json") or {}
        atributos = contenido.get("atributos") or {}
        info_estilo = atributos.get("_styleInfo") or {}

        estilo = TableStyleInfo(
            name=info_estilo.get("name") or "TableStyleMedium2",
            showFirstColumn=_bool(info_estilo.get("showFirstColumn"), False),
            showLastColumn=_bool(info_estilo.get("showLastColumn"), False),
            showRowStripes=_bool(info_estilo.get("showRowStripes"), True),
            showColumnStripes=_bool(info_estilo.get("showColumnStripes"), False),
        )

        columnas = [
            {"id": indice + 1, "name": columna.get("name") or f"Columna{indice + 1}"}
            for indice, columna in enumerate(contenido.get("columnas") or [])
        ]

        try:
            objeto = Table(displayName=nombre, ref=referencia, tableStyleInfo=estilo)
            if columnas:
                from openpyxl.worksheet.table import TableColumn

                objeto.tableColumns = [TableColumn(**columna) for columna in columnas]
            ws.add_table(objeto)
        except (TypeError, ValueError) as error:
            reporte.degradado(
                "tables", f"tabla '{nombre}' no reconstruible: {error}", ws.title
            )


def _aplicar_comentarios(ws, comentarios, opciones):
    """
    Comentarios.

    La caja del comentario se conserva siempre (es formato: autor y posicion);
    el texto depende de `keep_comment_text`, que por defecto es False porque
    el texto de un comentario es contenido.
    """

    if not comentarios:
        return

    from openpyxl.comments import Comment

    for comentario in comentarios:
        celda = comentario.get("cell_ref")
        if not celda:
            continue

        texto = comentario.get("text") if opciones.keep_comment_text else None

        if texto:
            ws[celda].comment = Comment(texto, autor=comentario.get("author") or "")
        # Sin texto no se puede crear un comentario: Excel no admite uno vacio.
        # Se omite en vez de escribir un comentario sin cuerpo, que es lo que
        # marcaria el archivo como danado.


def _aplicar_imagenes(ws, imagenes, reporte):
    """
    Imagenes: Fase 1 no las reexporta.

    El binario no se copio a la base, solo el ancla. Dejar una referencia sin
    archivo produciria un `.xlsx` que Excel marca como danado, asi que se
    declaran en el reporte y la plantilla sale sin ellas.
    """

    if imagenes:
        reporte.degradado(
            "images",
            f"{len(imagenes)} imagenes presentes en el original: Fase 1 no las reexporta",
            ws.title,
        )


# --------------------------------------------------------------------- #
# Impresion
# --------------------------------------------------------------------- #

def _aplicar_impresion(ws, hoja, reporte):
    """`pageSetup`, margenes, encabezado/pie, area y titulos de impresion."""

    configuracion = hoja.get("page_setup_json") or {}

    if configuracion:
        _aplicar_page_setup(ws, configuracion, reporte)

    margenes = hoja.get("margins_json")
    if margenes:
        from openpyxl.worksheet.page import PageMargins

        ws.page_margins = PageMargins(
            left=_float(margenes.get("left"), 0.7),
            right=_float(margenes.get("right"), 0.7),
            top=_float(margenes.get("top"), 0.75),
            bottom=_float(margenes.get("bottom"), 0.75),
            header=_float(margenes.get("header"), 0.3),
            footer=_float(margenes.get("footer"), 0.3),
        )

    encabezado_pie = hoja.get("header_footer_json")
    if encabezado_pie:
        from openpyxl.worksheet.header_footer import HeaderFooter

        ws.oddHeader = encabezado_pie.get("oddHeader")
        ws.oddFooter = encabezado_pie.get("oddFooter")
        ws.evenHeader = encabezado_pie.get("evenHeader")
        ws.evenFooter = encabezado_pie.get("evenFooter")
        ws.firstHeader = encabezado_pie.get("firstHeader")
        ws.firstFooter = encabezado_pie.get("firstFooter")
        ws.HeaderFooter = HeaderFooter(
            differentOddEven=_bool(encabezado_pie.get("diferentOddEven"), False),
            differentFirst=_bool(encabezado_pie.get("diferentFirst"), False),
            alignWithMargins=_bool(encabezado_pie.get("alignWithMargins"), True),
            scaleWithDoc=_bool(encabezado_pie.get("scaleWithDoc"), True),
        )

    area = (hoja.get("print_json") or {}).get("print_area")
    if area:
        ws.print_area = _normalizar_area(area, hoja["name"])

    titulos = hoja.get("print_title")
    if titulos:
        if titulos.get("rows"):
            ws.print_title_rows = titulos["rows"]
        if titulos.get("cols"):
            ws.print_title_cols = titulos["cols"]


def _aplicar_page_setup(ws, configuracion, reporte):
    """Orientacion, papel y ajuste a la pagina, leyendo los atributos crudos."""

    # `orientation` y `paperSize` llegan como strings del XML.
    orientacion = configuracion.get("orientation")
    if orientacion:
        ws.page_setup.orientation = orientacion

    papel = _int(configuracion.get("paperSize"))
    if papel is not None:
        ws.page_setup.paperSize = papel

    if _bool(configuracion.get("fitToPage")):
        ws.page_setup.fitToPage = True

    escala = _int(configuracion.get("scale"))
    if escala is not None:
        ws.page_setup.scale = escala

    ajustar_ancho = _int(configuracion.get("fitToWidth"))
    if ajustar_ancho is not None:
        ws.page_setup.fitToWidth = ajustar_ancho

    ajustar_alto = _int(configuracion.get("fitToHeight"))
    if ajustar_alto is not None:
        ws.page_setup.fitToHeight = ajustar_alto

    # `horizontalDpi`/`verticalDpi` no tienen equivalente en openpyxl; se
    # declaran para que quede constancia.
    for clave in ("horizontalDpi", "verticalDpi", "blackAndWhite", "draft"):
        if clave in configuracion:
            continue

    # Los `.bin` de impresora se descartan a proposito: son un blob opaco que
    # solo describe la impresora del equipo que guardo el archivo, y meterlos
    # en la base no aportaria nada al formato en pantalla.


def _normalizar_area(area, nombre_hoja):
    """
    El area de impresion viene como `'Hoja1'!$A$1:$AP$1921`.

    openpyxl la espera sin el nombre de hoja, asi que se quita.
    """

    if "!" in area:
        area = area.split("!", 1)[1]
    return area.replace("$", "")


def _float(valor, defecto):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def _int(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------- #
# Nombres definidos
# --------------------------------------------------------------------- #

def _aplicar_nombres_definidos(libro, modelo, reporte):
    """
    `definedNames` del libro.

    Los nombres de Excel automaticos (`_xlnm.Print_Area`, `_xlnm.Print_Titles`)
    no se reescriben aqui: openpyxl los genera desde `ws.print_area` y
    `ws.print_title_*`. Los demas si, porque son formulas que el usuario
    puede usar.
    """

    nombres = (modelo.get("workbook") or {}).get("defined_names") or []

    for nombre in nombres:
        if nombre.get("name", "").startswith("_xlnm."):
            continue

        try:
            libro.defined_names.add(
                openpyxl_nombre(nombre["name"], nombre.get("value") or "")
            )
        except (AttributeError, TypeError, ValueError) as error:
            reporte.degradado(
                "defined_names",
                f"nombre definido '{nombre.get('name')}' no reexportable: {error}",
            )


def openpyxl_nombre(nombre, valor):
    """Construye un `DefinedName` de openpyxl."""

    from openpyxl.workbook.defined_name import DefinedName

    return DefinedName(nombre, attr_text=valor)
