"""
Lectura directa del XML de un `.xlsx`/`.xlsm`.

Un `.xlsx` es un ZIP de XML. openpyxl cubre casi todo, pero hay cosas que no
expone o expone incompletas, y este modulo las lee del crudo:

- `theme1.xml` (la paleta que da sentido a los colores `theme`),
- `sheetView` completo (panel inmovilizado con `xSplit`/`ySplit` atypicos,
  `zoomScale`, `showGridLines`, pestanas seleccionadas),
- `conditionalFormatting` con el `sqref` literal y el `dxfId` original,
- `dxfs` completos,
- `autoFilter` con `filterColumn` y `sortState`,
- `cols`, `row` (atributos crudos),
- `mergeCells`, `dataValidations`, `tableParts`, `legacyDrawing`,
- `definedNames` del libro.

Se lee con `ElementTree` sobre el bytes del ZIP. No se reescribe ningun XML
aqui: esto solo extrae, y quien reconstruye el archivo es `render`.
"""

import re
import zipfile
from xml.etree import ElementTree as ET

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_DRAWING_SS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"


def _ns(tag, ns=NS_MAIN):
    return f"{{{ns}}}{tag}"


def _texto(elemento):
    if elemento is None:
        return None
    return elemento.text if elemento.text is not None else ""


class RawWorkbook:
    """
    Acceso al XML crudo de un libro ya abierto en memoria.

    El `ZipFile` se mantiene abierto mientras dure la extraccion. Se usa como
    context manager para no dejar el descriptor suelto:

        with RawWorkbook(ruta) as libro:
            ...
    """

    def __init__(self, ruta):
        self.ruta = ruta
        self._zip = zipfile.ZipFile(ruta, "r")
        # Dos caches separadas a proposito: los bytes de una entrada y su XML
        # parseado son cosas distintas, y compartir cache hacia a que `xml()`
        # devuelva bytes crudos.
        self._bytes = {}
        self._arboles = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def close(self):
        if self._zip is not None:
            self._zip.close()
            self._zip = None

    # ------------------------------------------------------------------ #
    # Acceso al ZIP
    # ------------------------------------------------------------------ #

    def nombres(self):
        """Lista de rutas internas del paquete."""

        return self._zip.namelist()

    def existe(self, nombre):
        return nombre in self._zip.namelist()

    def leer_bytes(self, nombre):
        """Bytes crudos de una entrada del ZIP, o None si no existe."""

        if nombre not in self._bytes:
            try:
                self._bytes[nombre] = self._zip.read(nombre)
            except KeyError:
                self._bytes[nombre] = None
        return self._bytes[nombre]

    def leer_texto(self, nombre):
        datos = self.leer_bytes(nombre)
        if datos is None:
            return None
        return datos.decode("utf-8", errors="replace")

    def xml(self, nombre):
        """Parsea una entrada como ElementTree, cacheando el resultado."""

        if nombre not in self._arboles:
            datos = self.leer_bytes(nombre)
            if datos is None:
                self._arboles[nombre] = None
            else:
                try:
                    self._arboles[nombre] = ET.fromstring(datos)
                except ET.ParseError:
                    self._arboles[nombre] = None
        return self._arboles[nombre]

    # ------------------------------------------------------------------ #
    # theme
    # ------------------------------------------------------------------ #

    def theme_xml(self):
        """`theme/theme1.xml` tal cual, para reaplicarlo al exportar."""

        return self.leer_texto("xl/theme/theme1.xml")

    def paleta_tema(self):
        """
        Paleta del tema como lista de strings ARGB.

        Sirve para calcular un RGB aproximado en comparaciones. La fuente de
        verdad al exportar sigue siendo el XML crudo.

        Ojo: `theme1.xml` esta en el namespace de DrawingML, no en el de
        SpreadsheetML, asi que las etiquetas se buscan con su propio namespace.
        """

        raiz = self.xml("xl/theme/theme1.xml")
        if raiz is None:
            return []

        esquema = raiz.find(f".//{{{NS_DRAWING}}}clrScheme")
        if esquema is None:
            return []

        colores = []
        for hijo in esquema:
            # Cada color es un <srgbClr val="..."/>, <sysClr lastClr="..."/>,
            # <hslClr hue=.../> u otro; se toma lo que exista.
            srgb = hijo.find(f"{{{NS_DRAWING}}}srgbClr")
            if srgb is not None and srgb.get("val"):
                colores.append("FF" + srgb.get("val").upper())
                continue

            sistema = hijo.find(f"{{{NS_DRAWING}}}sysClr")
            if sistema is not None:
                ultimo = sistema.get("lastClr")
                if ultimo:
                    colores.append("FF" + ultimo.upper())
                    continue

            colores.append(None)

        return colores

    # ------------------------------------------------------------------ #
    # workbook
    # ------------------------------------------------------------------ #

    def workbook_xml(self):
        return self.xml("xl/workbook.xml")

    def hojas_en_orden(self):
        """
        Hojas en el orden real del libro, con su `r:id` y su parte destino.

        Confiar en el orden de `<sheets>` es obligatorio: el orden de las hojas
        visibles es parte del formato que hay que reproducir.
        """

        raiz = self.workbook_xml()
        if raiz is None:
            return []

        relaciones = self._relaciones("xl/_rels/workbook.xml.rels")

        resultado = []
        hojas = raiz.find(_ns("sheets"))
        if hojas is None:
            return []

        for hoja in hojas.findall(_ns("sheet")):
            rid = hoja.get(_ns("id", NS_REL))
            destino = relaciones.get(rid, "")
            resultado.append(
                {
                    "name": hoja.get("name"),
                    "sheetId": hoja.get("sheetId"),
                    "state": hoja.get("state") or "visible",
                    "r:id": rid,
                    "target": destino,
                    "path": _normalizar_ruta("xl", destino),
                }
            )

        return resultado

    def defined_names(self):
        """`definedNames` del libro, con sus atributos literales."""

        raiz = self.workbook_xml()
        if raiz is None:
            return []

        contenedor = raiz.find(_ns("definedNames"))
        if contenedor is None:
            return []

        nombres = []
        for nombre in contenedor.findall(_ns("definedName")):
            # Un definedName puede traer <extLst> con datos de extension; se
            # guarda el texto literal, que es lo que Excel interpreta.
            nombres.append(
                {
                    "name": nombre.get("name"),
                    "localSheetId": nombre.get("localSheetId"),
                    "hidden": nombre.get("hidden") in ("1", "true"),
                    "value": _texto(nombre) or "",
                }
            )
        return nombres

    def props(self):
        """`docProps/core.xml` y `app.xml` como dicts."""

        return {
            "core": self._props_core(),
            "app": self._props_app(),
        }

    def _props_core(self):
        raiz = self.xml("docProps/core.xml")
        if raiz is None:
            return {}
        # core.xml usa namespace de propiedades, no el principal.
        resultado = {}
        for hijo in list(raiz):
            clave = hijo.tag.split("}")[-1]
            resultado[clave] = hijo.text or ""
        return resultado

    def _props_app(self):
        raiz = self.xml("docProps/app.xml")
        if raiz is None:
            return {}
        resultado = {}
        for hijo in list(raiz):
            clave = hijo.tag.split("}")[-1]
            valor = (hijo.text or "").strip()
            if valor:
                resultado[clave] = valor
        return resultado

    def calc_props(self):
        """`calcPr` del libro (por ejemplo `fullCalcOnLoad`)."""

        raiz = self.workbook_xml()
        if raiz is None:
            return {}
        nodo = raiz.find(_ns("calcPr"))
        if nodo is None:
            return {}
        return dict(nodo.attrib)

    # ------------------------------------------------------------------ #
    # relaciones
    # ------------------------------------------------------------------ #

    def _relaciones(self, ruta_rels):
        """Mapa `rId` -> target, normalizado a ruta interna del paquete."""

        raiz = self.xml(ruta_rels)
        if raiz is None:
            return {}

        mapa = {}
        for relacion in raiz:
            mapa[relacion.get("Id")] = relacion.get("Target")
        return mapa

    def relacion_de_hoja(self, indice):
        """Parte XML de la hoja n-esima (1-based, como la nombra Excel)."""

        hojas = self.hojas_en_orden()
        if 1 <= indice <= len(hojas):
            return hojas[indice - 1]["path"]
        return None

    # ------------------------------------------------------------------ #
    # hoja
    # ------------------------------------------------------------------ #

    def sheet_xml(self, ruta_hoja):
        return self.xml(ruta_hoja)

    def sheet_view(self, ruta_hoja):
        """
        `sheetViews/sheetView` de la hoja, con sus hijos literales.

        Devuelve el primer `sheetView` (el que Excel considera vigente) con
        `pane` y `selection` anidados como dicts. Se lee aqui porque
        `ws.freeze_panes` de openpyxl solo cubre el caso tipico y el ejemplo
        tiene paneles con `xSplit`/`ySplit` atipicos.
        """

        raiz = self.sheet_xml(ruta_hoja)
        if raiz is None:
            return {}

        vistas = raiz.find(_ns("sheetViews"))
        if vistas is None:
            return {}

        vista = vistas.find(_ns("sheetView"))
        if vista is None:
            return {}

        resultado = dict(vista.attrib)

        panel = vista.find(_ns("pane"))
        if panel is not None:
            resultado["pane"] = dict(panel.attrib)

        seleccion = vista.find(_ns("selection"))
        if seleccion is not None:
            resultado["selection"] = dict(seleccion.attrib)

        return resultado

    def cols(self, ruta_hoja):
        """`<col>` crudos: min, max, width, style, hidden, customWidth, bestFit, outlineLevel."""

        raiz = self.sheet_xml(ruta_hoja)
        if raiz is None:
            return []

        contenedor = raiz.find(_ns("cols"))
        if contenedor is None:
            return []

        columnas = []
        for col in contenedor.findall(_ns("col")):
            columnas.append(dict(col.attrib))
        return columnas

    def filas(self, ruta_hoja):
        """`<row>` crudos con sus atributos, sin entrar en las celdas."""

        raiz = self.sheet_xml(ruta_hoja)
        if raiz is None:
            return []

        filas = []
        for fila in raiz.findall(f"{_ns('sheetData')}/{_ns('row')}"):
            atributos = dict(fila.attrib)
            if atributos:
                filas.append(atributos)
        return filas

    def merged_ranges(self, ruta_hoja):
        """Lista de rangos combinados, en el orden del archivo."""

        raiz = self.sheet_xml(ruta_hoja)
        if raiz is None:
            return []

        contenedor = raiz.find(_ns("mergeCells"))
        if contenedor is None:
            return []

        rangos = []
        for celda in contenedor.findall(_ns("mergeCell")):
            ref = celda.get("ref")
            if ref:
                rangos.append(ref)
        return rangos

    def conditional_formats(self, ruta_hoja):
        """
        Reglas de formato condicional tal cual aparecen en el archivo.

        Devuelve la lista de bloques `<conditionalFormatting>`, cada uno con su
        `sqref` literal (la lista de rangos, sin normalizar) y sus reglas con
        todos los atributos y subnodos reconocidos.
        """

        raiz = self.sheet_xml(ruta_hoja)
        if raiz is None:
            return []

        bloques = []
        for bloque in raiz.findall(_ns("conditionalFormatting")):
            reglas = []
            for regla in bloque.findall(_ns("cfRule")):
                reglas.append(self._leer_regla_cf(regla))
            bloques.append({"sqref": bloque.get("sqref") or "", "rules": reglas})
        return bloques

    def _leer_regla_cf(self, regla):
        """Vuelca una `<cfRule>` a dict, incluidos colorScale/dataBar/iconSet."""

        datos = dict(regla.attrib)

        formulas = [f.text or "" for f in regla.findall(_ns("formula"))]
        if formulas:
            datos["formula"] = formulas

        color_scale = regla.find(_ns("colorScale"))
        if color_scale is not None:
            colores = []
            for color in color_scale.findall(_ns("color")):
                colores.append(dict(color.attrib))
            datos["colorScale"] = {
                "cfvo": [dict(c.attrib) for c in color_scale.findall(_ns("cfvo"))],
                "color": colores,
            }

        data_bar = regla.find(_ns("dataBar"))
        if data_bar is not None:
            datos["dataBar"] = {
                "cfvo": [dict(c.attrib) for c in data_bar.findall(_ns("cfvo"))],
                "color": [dict(c.attrib) for c in data_bar.findall(_ns("color"))],
            }

        icon_set = regla.find(_ns("iconSet"))
        if icon_set is not None:
            datos["iconSet"] = {
                "iconSet": icon_set.get("iconSet"),
                "showValue": icon_set.get("showValue"),
                "reverse": icon_set.get("reverse"),
                "cfvo": [dict(c.attrib) for c in icon_set.findall(_ns("cfvo"))],
            }

        return datos

    def dxfs(self):
        """
        Lista de `<dxf>` del libro, en orden de indice.

        El indice de la lista es el `dxfId` al que apuntan las reglas de formato
        condicional, asi que el orden no se puede alterar.
        """

        raiz = self.xml("xl/styles.xml")
        if raiz is None:
            return []

        contenedor = raiz.find(_ns("dxfs"))
        if contenedor is None:
            return []

        return [self._leer_dxf(dxf) for dxf in contenedor.findall(_ns("dxf"))]

    def _leer_dxf(self, dxf):
        """
        Un `<dxf>` a dict.

        openpyxl expone los dxf con un modelo parecido pero no siempre igual
        (sobre todo en fuentes y bordes), asi que se leen del crudo para no
        perder `theme`+`tint` ni los atributos de borde por lado.
        """

        from .colors import desde_xml

        resultado = {}

        fuente = dxf.find(_ns("font"))
        if fuente is not None:
            resultado["font"] = self._leer_dxf_fuente(fuente, desde_xml)

        relleno = dxf.find(_ns("fill"))
        if relleno is not None:
            resultado["fill"] = self._leer_dxf_relleno(relleno, desde_xml)

        borde = dxf.find(_ns("border"))
        if borde is not None:
            resultado["border"] = self._leer_dxf_borde(borde)

        numero = dxf.find(_ns("numFmt"))
        if numero is not None:
            resultado["numFmt"] = {
                "numFmtId": numero.get("numFmtId"),
                "formatCode": numero.get("formatCode"),
            }

        alineacion = dxf.find(_ns("alignment"))
        if alineacion is not None:
            resultado["alignment"] = dict(alineacion.attrib)

        proteccion = dxf.find(_ns("protection"))
        if proteccion is not None:
            resultado["protection"] = dict(proteccion.attrib)

        return resultado

    def _leer_dxf_fuente(self, fuente, desde_xml):
        datos = {}
        for nombre in (
            "b", "i", "u", "strike", "outline", "shadow", "condense", "extend",
        ):
            nodo = fuente.find(_ns(nombre))
            if nodo is not None:
                datos[nombre] = nodo.get("val") in ("1", "true", None)

        tamano = fuente.find(_ns("sz"))
        if tamano is not None:
            datos["sz"] = tamano.get("val")

        nombre = fuente.find(_ns("name"))
        if nombre is not None:
            datos["name"] = nombre.get("val")

        familia = fuente.find(_ns("family"))
        if familia is not None:
            datos["family"] = familia.get("val")

        esquema = fuente.find(_ns("scheme"))
        if esquema is not None:
            datos["scheme"] = esquema.get("val")

        vert = fuente.find(_ns("vertAlign"))
        if vert is not None:
            datos["vertAlign"] = vert.get("val")

        color = fuente.find(_ns("color"))
        if color is not None:
            datos["color"] = desde_xml(color.attrib)

        return datos

    def _leer_dxf_relleno(self, relleno, desde_xml):
        patron = relleno.find(_ns("patternFill"))
        if patron is None:
            gradiente = relleno.find(_ns("gradientFill"))
            if gradiente is not None:
                return {
                    "kind": "gradient",
                    "degree": gradiente.get("degree"),
                    "type": gradiente.get("type"),
                    "stop": [
                        {"position": e.get("position"), "color": desde_xml(e.attrib)}
                        for e in gradiente.findall(_ns("stop"))
                    ],
                }
            return {}

        datos = {"kind": "pattern", "patternType": patron.get("patternType")}

        fg = patron.find(_ns("fgColor"))
        if fg is not None:
            datos["fgColor"] = desde_xml(fg.attrib)

        bg = patron.find(_ns("bgColor"))
        if bg is not None:
            datos["bgColor"] = desde_xml(bg.attrib)

        return datos

    def _leer_dxf_borde(self, borde):
        datos = {}
        for lado in ("left", "right", "top", "bottom", "diagonal"):
            nodo = borde.find(_ns(lado))
            if nodo is None:
                continue
            lado_datos = {}
            if nodo.get("style"):
                lado_datos["style"] = nodo.get("style")
            color = nodo.find(_ns("color"))
            if color is not None:
                lado_datos["color"] = color.attrib
            if lado_datos:
                datos[lado] = lado_datos
        return datos

    def auto_filter(self, ruta_hoja):
        """
        `<autoFilter>` con `ref`, `filterColumn` y `sortState` literales.

        `hidden_rows` (las filas que el archivo trae ocultas por el filtro) no
        estan en el XML del filtro: se deducen de `<row hidden="1">` y las
        guarda `extract.autofilter`.
        """

        raiz = self.sheet_xml(ruta_hoja)
        if raiz is None:
            return None

        filtro = raiz.find(_ns("autoFilter"))
        if filtro is None:
            return None

        resultado = {"ref": filtro.get("ref") or "", "columns": [], "sortState": None}

        for columna in filtro.findall(_ns("filterColumn")):
            datos = dict(columna.attrib)

            filtros = columna.find(_ns("filters"))
            if filtros is not None:
                datos["filters"] = {
                    "blank": filtros.get("blank") in ("1", "true"),
                    "showButton": filtros.get("showButton"),
                    "vals": [v.get("val") for v in filtros.findall(_ns("filter"))],
                }

            personalizado = columna.find(_ns("customFilters"))
            if personalizado is not None:
                datos["customFilters"] = [
                    {
                        "operator": c.get("operator"),
                        "val": c.get("val"),
                    }
                    for c in personalizado.findall(_ns("customFilter"))
                ]

            dinamicos = columna.find(_ns("dynamicFilter"))
            if dinamicos is not None:
                datos["dynamicFilter"] = dict(dinamicos.attrib)

            color = columna.find(_ns("colorFilter"))
            if color is not None:
                datos["colorFilter"] = dict(color.attrib)

            iconos = columna.find(_ns("iconFilter"))
            if iconos is not None:
                datos["iconFilter"] = dict(iconos.attrib)

            top10 = columna.find(_ns("top10"))
            if top10 is not None:
                datos["top10"] = dict(top10.attrib)

            resultado["columns"].append(datos)

        orden = filtro.find(_ns("sortState"))
        if orden is not None:
            resultado["sortState"] = {
                "columnSort": orden.get("columnSort") in ("1", "true"),
                "caseSensitive": orden.get("caseSensitive") in ("1", "true"),
                "sortMethod": orden.get("sortMethod"),
                "ref": orden.get("ref"),
                "sortCondition": [
                    dict(c.attrib) for c in orden.findall(_ns("sortCondition"))
                ],
            }

        return resultado

    def data_validations(self, ruta_hoja):
        """`<dataValidation>` crudos con sus `formula1`/`formula2`."""

        raiz = self.sheet_xml(ruta_hoja)
        if raiz is None:
            return []

        contenedor = raiz.find(_ns("dataValidations"))
        if contenedor is None:
            return []

        resultado = []
        for dv in contenedor.findall(_ns("dataValidation")):
            datos = dict(dv.attrib)
            f1 = dv.find(_ns("formula1"))
            f2 = dv.find(_ns("formula2"))
            if f1 is not None:
                datos["formula1"] = f1.text or ""
            if f2 is not None:
                datos["formula2"] = f2.text or ""
            resultado.append(datos)
        return resultado

    def print_area_y_titulos(self, ruta_hoja):
        """Del XML de la hoja: area de impresion y saltos de pagina."""

        raiz = self.sheet_xml(ruta_hoja)
        if raiz is None:
            return {}

        configuracion = raiz.find(_ns("pageSetup"))
        margenes = raiz.find(_ns("pageMargins"))
        encabezado_pie = raiz.find(_ns("headerFooter"))

        resultado = {}
        if configuracion is not None:
            resultado["pageSetup"] = dict(configuracion.attrib)
        if margenes is not None:
            resultado["pageMargins"] = dict(margenes.attrib)
        if encabezado_pie is not None:
            resultado["headerFooter"] = {
                "diferentOddEven": encabezado_pie.get("differentOddEven"),
                "diferentFirst": encabezado_pie.get("differentFirst"),
                "scaleWithDoc": encabezado_pie.get("scaleWithDoc"),
                "alignWithMargins": encabezado_pie.get("alignWithMargins"),
                "oddHeader": (encabezado_pie.find(_ns("oddHeader")).text
                              if encabezado_pie.find(_ns("oddHeader")) is not None else None),
                "oddFooter": (encabezado_pie.find(_ns("oddFooter")).text
                              if encabezado_pie.find(_ns("oddFooter")) is not None else None),
                "evenHeader": (encabezado_pie.find(_ns("evenHeader")).text
                               if encabezado_pie.find(_ns("evenHeader")) is not None else None),
                "evenFooter": (encabezado_pie.find(_ns("evenFooter")).text
                               if encabezado_pie.find(_ns("evenFooter")) is not None else None),
                "firstHeader": (encabezado_pie.find(_ns("firstHeader")).text
                                if encabezado_pie.find(_ns("firstHeader")) is not None else None),
                "firstFooter": (encabezado_pie.find(_ns("firstFooter")).text
                                if encabezado_pie.find(_ns("firstFooter")) is not None else None),
            }

        return resultado

    def print_titles(self, ruta_hoja, defined_names):
        """
        `print_title_rows`/`print_title_cols` resueltos desde los definedNames.

        Excel no los guarda en la hoja: son definedNames con `localSheetId`
        apuntando a la hoja y nombre `_xlnm.Print_Titles`.
        """

        raiz = self.sheet_xml(ruta_hoja)
        if raiz is None:
            return {}

        # Indice de la hoja dentro del libro (0-based en localSheetId).
        indice = self._indice_local_de_hoja(ruta_hoja)

        area = None
        titulos = None
        for nombre in defined_names or []:
            if nombre.get("localSheetId") is None:
                continue
            if int(nombre["localSheetId"]) != indice:
                continue

            valor = nombre.get("value") or ""
            if nombre.get("name") == "_xlnm.Print_Area":
                area = valor
            elif nombre.get("name") == "_xlnm.Print_Titles":
                titulos = valor

        return {"print_area": area, "print_titles": titulos}

    def _indice_local_de_hoja(self, ruta_hoja):
        for indice, hoja in enumerate(self.hojas_en_orden()):
            if hoja["path"] == ruta_hoja:
                return indice
        return -1

    def comments_xml(self, ruta_hoja):
        """XML de comentarios de la hoja, o None si no tiene."""

        relaciones = self._relaciones(_rels_de(ruta_hoja))

        for destino in relaciones.values():
            if "comments" in destino and destino.endswith(".xml"):
                return self.xml(_normalizar_ruta("xl", destino))

        return None

    def autores_de_comentarios(self, ruta_comments):
        """Autores declarados en el XML de comentarios, en orden."""

        if not ruta_comments:
            return []

        raiz = self.xml(ruta_comments)
        if raiz is None:
            return []

        autores = []
        for autor in raiz.findall(f"{_ns('authors')}/{_ns('author')}"):
            autores.append(autor.text or "")
        return autores

    def tabla_por_relacion(self, ruta_hoja):
        """`tableParts` de la hoja: nombres de las tablas que declara."""

        raiz = self.sheet_xml(ruta_hoja)
        if raiz is None:
            return []

        partes = raiz.find(_ns("tableParts"))
        if partes is None:
            return []

        relaciones = self._relaciones(_rels_de(ruta_hoja))
        resultado = []
        for parte in partes.findall(_ns("tablePart")):
            rid = parte.get(_ns("id", NS_REL))
            destino = relaciones.get(rid)
            if destino:
                resultado.append(_normalizar_ruta("xl", destino))
        return resultado

    def drawing_de_hoja(self, ruta_hoja):
        """`drawing` de la hoja o None."""

        raiz = self.sheet_xml(ruta_hoja)
        if raiz is None:
            return None
        nodo = raiz.find(_ns("drawing"))
        if nodo is None:
            return None
        rid = nodo.get(_ns("id", NS_REL))
        if not rid:
            return None
        relaciones = self._relaciones(_rels_de(ruta_hoja))
        destino = relaciones.get(rid)
        return _normalizar_ruta("xl", destino) if destino else None


def _rels_de(ruta_hoja):
    """Ruta del `.rels` que acompaña a una parte del paquete."""

    carpeta, archivo = _dividir(ruta_hoja)
    return f"{carpeta}/_rels/{archivo}.rels" if carpeta else f"_rels/{archivo}.rels"


def _dividir(ruta):
    carpeta, _, archivo = ruta.rpartition("/")
    return carpeta, archivo


def _normalizar_ruta(base, destino):
    """Resuelve un target de relacion a ruta interna del paquete."""

    if not destino:
        return None

    if destino.startswith("/"):
        return destino.lstrip("/")

    partes = []
    for segmento in f"{base}/{destino}".split("/"):
        if segmento in ("", "."):
            continue
        if segmento == "..":
            if partes:
                partes.pop()
            continue
        partes.append(segmento)

    return "/".join(partes)


_RE_COL = re.compile(r"^([A-Z]+)(\d+)$")


def columna_a_indice(letras):
    """`A` -> 1, `B` -> 2, ... `AA` -> 27. Base 1, como en openpyxl."""

    indice = 0
    for caracter in letras:
        indice = indice * 26 + (ord(caracter) - 64)
    return indice


def indice_a_columna(indice):
    """1 -> `A`, 27 -> `AA`. Inversa de `columna_a_indice`."""

    letras = ""
    while indice > 0:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def parsear_ref(ref):
    """`A1:C1047436` -> (1, 1, 3, 1047436) en (fila, col) base 1."""

    if not ref or ":" not in ref:
        return None

    inicio, _, fin = ref.partition(":")
    match_inicio = _RE_COL.match(inicio)
    match_fin = _RE_COL.match(fin or inicio)

    if not match_inicio or not match_fin:
        return None

    fila_inicio = int(match_inicio.group(2))
    col_inicio = columna_a_indice(match_inicio.group(1))
    fila_fin = int(match_fin.group(2))
    col_fin = columna_a_indice(match_fin.group(1))

    return (fila_inicio, col_inicio, fila_fin, col_fin)