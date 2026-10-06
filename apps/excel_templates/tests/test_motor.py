"""
Pruebas del motor de plantillas Excel.

Los tests se organizan en dos bloques:

1. **Archivo de referencia** (`ZONA_PAGA_V764_MARTES.XLSX`, en `fixtures/`):
   captura, exporta y compara celda por celda. Es el caso real.
2. **Archivo sintetico** (`tests/generador.py`): un Excel distinto, con
   combinaciones, validacion de datos, tabla, filtro con criterios activos y
   filas ocultas. Demuestra que el motor es generico y no esta ajustado al
   archivo de referencia.

El archivo de referencia se salta si no esta en `fixtures/`: el `.xlsx` real no
se versiona (esta en `.gitignore`) y un CI recien clonado no lo tiene. Los
tests del sintetico siempre corren, asi que el motor no queda sin cobertura.
"""

import io
import os
import tempfile
import unittest
from xml.etree import ElementTree

from django.test import TestCase

from apps.excel_templates import extract, models, raw, services
from apps.excel_templates.options import ExportOptions, OpcionNoSoportada
from apps.excel_templates.styles import RegistroEstilos

from . import comparador
from .generador import construir as construir_sintetico

#: Raiz del repositorio, para localizar `fixtures/`.
RAIZ = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
)

RUTA_FIXTURE = os.path.join(RAIZ, "fixtures", "ZONA_PAGA_V764_MARTES.XLSX")

NOMBRE_PLANTILLA = "Versión Zona Paga"

# --------------------------------------------------------------------------- #
# Un `.xlsx` minimo escrito a mano, con una hoja que declara un rango enorme y
# solo tiene dos celdas dispersas. Se arma con `zipfile` porque justamente lo
# que se quiere comprobar es como se comporta el motor con un archivo que
# openpyxl no puede escribir bien: una celda en la fila 1 y otra en la 1047436.
# --------------------------------------------------------------------------- #

_TIPOS_DE_CONTENIDO = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    "</Types>"
)

_RAIZ_DE_RELACIONES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)

_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="Hoja1" sheetId="1" r:id="rId1"/></sheets>'
    "</workbook>"
)

_RELACIONES_DEL_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    "</Relationships>"
)

# `<dimension>` declara hasta la fila 1047436, pero solo hay dos celdas.
_HOJA_DISPERSA = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<dimension ref="A1:C1047436"/>'
    "<sheetData>"
    '<row r="1"><c r="A1" t="inlineStr"><is><t>encabezado</t></is></c></row>'
    '<row r="1047436"><c r="C1047436"><v>1</v></c></row>'
    "</sheetData>"
    "</worksheet>"
)


def _fixture_disponible():
    return os.path.exists(RUTA_FIXTURE)


class BaseTemporal(TestCase):
    """Base con un directorio temporal para los archivos de prueba."""

    def setUp(self):
        super().setUp()
        self._temporal = tempfile.TemporaryDirectory()
        self.temporal = self._temporal.name
        self.addCleanup(self._temporal.cleanup)

    def ruta(self, nombre):
        return os.path.join(self.temporal, nombre)


class TestEstilosPorFilaYColumna(TestCase):
    """Los estilos declarados directamente en XML se pueden resolver."""

    def test_resuelve_un_xf_crudo_sin_nameerror(self):
        estilos = ElementTree.fromstring(
            """
            <styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <fonts count="1">
                <font><name val="Arial"/><sz val="10"/></font>
              </fonts>
              <fills count="1">
                <fill><patternFill patternType="none"/></fill>
              </fills>
              <borders count="1">
                <border><left/><right/><top/><bottom/><diagonal/></border>
              </borders>
              <cellXfs count="1">
                <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
              </cellXfs>
            </styleSheet>
            """
        )

        estilo = extract._resolver_indice_estilo(
            estilos, 0, RegistroEstilos()
        )

        self.assertIsNotNone(estilo)


# --------------------------------------------------------------------- #
# Sintetico: demuestra que el motor es generico
# --------------------------------------------------------------------- #

class TestMotorGenerico(BaseTemporal):
    """
    Captura y reexporta un Excel sintetico con caracteristicas distintas.

    Este archivo tiene celdas combinadas, validacion de datos, color de tema con
    tint, panel inmovilizado, color de pestana, formato condicional y un
    autofiltro con criterios activos y una fila oculta.
    """

    def setUp(self):
        super().setUp()
        self.ruta_original = self.ruta("sintetico.xlsx")
        construir_sintetico(self.ruta_original)

        # Dos archivos mas con el mismo formato pero distinto nombre de hoja.
        # `services.capturar` rechaza un archivo ya capturado (mismo SHA), asi
        # que cualquier prueba que quiera una segunda version necesita bytes
        # distintos. Cambiar el nombre de la hoja no toca ningun estilo, asi que
        # los hashes de estilo siguen siendo los mismos.
        self.segunda_ruta = self.ruta("sintetico-2.xlsx")
        construir_sintetico(self.segunda_ruta, hoja_datos="Datos2")

        self.tercera_ruta = self.ruta("sintetico-3.xlsx")
        construir_sintetico(self.tercera_ruta, hoja_datos="Datos3")

        self.captura = services.capturar(
            self.ruta_original,
            nombre="Plantilla Sintética",
            descripcion="Archivo de prueba del motor",
        )
        self.plantilla = self.captura["plantilla"]

    def _exportar(self, opciones=None):
        """Exporta y reabre con openpyxl para poder compararlo."""

        import openpyxl

        exportado = services.exportar(self.plantilla, opciones=opciones)

        salida = self.ruta("exportado.xlsx")
        with open(salida, "wb") as archivo:
            archivo.write(exportado["datos"])

        libro = openpyxl.load_workbook(salida)
        self.addCleanup(libro.close)

        return libro, exportado

    def _original(self):
        import openpyxl

        libro = openpyxl.load_workbook(self.ruta_original)
        self.addCleanup(libro.close)
        return libro

    # -- formato ----------------------------------------------------- #

    def test_el_archivo_se_captura_y_se_publica(self):
        self.assertEqual(self.plantilla.name, "Plantilla Sintética")
        self.assertIsNotNone(self.plantilla.current_version)
        self.assertEqual(self.plantilla.current_version.status, "VIGENTE")
        self.assertEqual(self.plantilla.current_version.version_no, 1)
        self.assertEqual(len(self.plantilla.current_version.source_sha256), 64)

    def test_el_nombre_de_exportacion_pasa_a_minusculas(self):
        """La extension se normaliza; el resto del nombre se respeta."""

        self.assertEqual(self.plantilla.export_filename, "sintetico.xlsx")

    def test_el_formato_coincide_celda_por_celda(self):
        """
        Criterio de aceptacion principal: cero diferencias de formato.

        Se ignoran los valores porque la plantilla sale sin datos, pero todo lo
        demas (fuente, relleno, bordes, alineacion, formato numerico,
        proteccion) tiene que ser identico.
        """

        original = self._original()
        exportado, _ = self._exportar()

        diferencias = comparador.comparar_hojas(original, exportado)

        self.assertEqual(
            diferencias,
            [],
            f"{len(diferencias)} diferencias de formato:\n"
            + "\n".join(diferencias[:40]),
        )

    def test_los_nombres_y_el_orden_de_hojas_se_conservan(self):
        original = self._original()
        exportado, _ = self._exportar()

        self.assertEqual(exportado.sheetnames, original.sheetnames)

    def test_una_hoja_alta_y_dispersa_no_se_recorre_entera(self):
        """
        Una hoja con celdas en la fila 1 y en la 1047436 no se recorre entera.

        `iter_rows()` crea una celda por cada hueco del rango, asi que usarlo
        aqui materializaria mas de un millon de objetos que el archivo no
        tiene. El extractor tiene que recorrer solo las celdas que existen, y
        este test falla en cuanto alguien vuelva a usar `iter_rows()`.
        """

        import zipfile

        import openpyxl

        from apps.excel_templates import extract

        ruta = os.path.join(tempfile.gettempdir(), "sparse.xlsx")

        with zipfile.ZipFile(ruta, "w") as paquete:
            paquete.writestr("[Content_Types].xml", _TIPOS_DE_CONTENIDO)
            paquete.writestr("_rels/.rels", _RAIZ_DE_RELACIONES)
            paquete.writestr("xl/workbook.xml", _WORKBOOK)
            paquete.writestr("xl/_rels/workbook.xml.rels", _RELACIONES_DEL_WORKBOOK)
            paquete.writestr("xl/worksheets/sheet1.xml", _HOJA_DISPERSA)

        # Si la extraccion vuelve a apoyarse en `iter_rows()`, el error salta
        # antes de poder colgarse en silencio.
        original_iter_rows = openpyxl.worksheet.worksheet.Worksheet.iter_rows

        def iter_rows_que_falla(self, *args, **kwargs):
            raise AssertionError(
                "la extraccion no debe usar iter_rows(): recorre celdas que "
                "el archivo no tiene"
            )

        openpyxl.worksheet.worksheet.Worksheet.iter_rows = iter_rows_que_falla
        self.addCleanup(
            setattr,
            openpyxl.worksheet.worksheet.Worksheet,
            "iter_rows",
            original_iter_rows,
        )

        modelo = extract.extraer(ruta, nombre="Dispersa")

        # La fila 1 es la unica con texto y no lleva estilo, asi que se vacia:
        # lo que se comprueba es que la hoja se leyo entera y sin explotar.
        self.assertEqual(len(modelo["hojas"]), 1)
        self.assertEqual(modelo["hojas"][0]["name"], "Hoja1")

    def test_los_anchos_de_columna_se_conservan(self):
        original = self._original()
        exportado, _ = self._exportar()

        for columna in ("A", "B", "C", "D", "E"):
            with self.subTest(columna=columna):
                self.assertAlmostEqual(
                    exportado["Datos"].column_dimensions[columna].width,
                    original["Datos"].column_dimensions[columna].width,
                    places=1,
                )

    def test_los_altos_de_fila_se_conservan(self):
        original = self._original()
        exportado, _ = self._exportar()

        for fila in (1, 2):
            with self.subTest(fila=fila):
                self.assertAlmostEqual(
                    exportado["Datos"].row_dimensions[fila].height,
                    original["Datos"].row_dimensions[fila].height,
                    places=1,
                )

    def test_el_color_de_tema_se_conserva_sin_resolver_a_rgb(self):
        """
        El relleno de la cabecera es un color de tema con tint.

        Si el motor lo resolviera a RGB, el color se veria parecido pero dejaria
        de responder al tema del libro. El test falla si eso ocurre.
        """

        from openpyxl import load_workbook

        exportado, _ = self._exportar()

        color = exportado["Datos"]["A1"].fill.fgColor

        self.assertEqual(
            color.type,
            "theme",
            f"el relleno de la cabecera deberia seguir siendo color de tema, "
            f"no {color.type}={color.value}",
        )
        self.assertIsNotNone(color.tint)
        del load_workbook

    def test_el_theme_del_original_se_reinyecta_en_el_exportado(self):
        """
        Un color `theme=4` solo significa algo si el theme es el del original.

        openpyxl escribe siempre su propio theme, asi que conservar el color
        como indice de tema sin reinyectar `theme1.xml` daria una plantilla que
        se ve con otros colores. Se compara el nombre del tema, que openpyxl
        lee del XML.
        """

        import zipfile

        from openpyxl.writer.theme import theme_xml as theme_por_defecto

        _, resultado = self._exportar()

        with zipfile.ZipFile(io.BytesIO(resultado["datos"])) as paquete:
            generado = paquete.read("xl/theme/theme1.xml").decode("utf-8")

        with zipfile.ZipFile(self.ruta_original) as paquete:
            original = paquete.read("xl/theme/theme1.xml").decode("utf-8")

        self.assertEqual(generado, original)
        self.assertNotEqual(generado, theme_por_defecto)

    def test_el_panel_inmovilizado_se_conserva(self):
        exportado, _ = self._exportar()

        panel = exportado["Datos"].sheet_view.pane

        self.assertIsNotNone(panel)
        self.assertEqual(panel.ySplit, 1)
        self.assertEqual(panel.topLeftCell, "A2")
        self.assertEqual(panel.state, "frozen")

    def test_el_color_de_pestana_se_conserva(self):
        from ..colors import desde_openpyxl

        exportado, _ = self._exportar()

        self.assertEqual(
            desde_openpyxl(exportado["Datos"].sheet_properties.tabColor),
            {"type": "rgb", "value": "FF00B050"},
        )

    def test_las_celdas_combinadas_se_conservan(self):
        exportado, _ = self._exportar()

        rangos = [str(r) for r in exportado["Datos"].merged_cells.ranges]

        self.assertIn("A13:C13", rangos)

    def test_la_tabla_se_conserva_con_su_rango_y_su_estilo(self):
        """
        Una tabla de Excel (`<table>`) no es lo mismo que un rango con formato.

        Hay que conservar nombre, rango y estilo de tabla: es lo que hace que
        Excel muestre los filtros de columna y las bandas de color.
        """

        exportado, _ = self._exportar()
        ws = exportado["Resumen"]

        self.assertEqual(len(ws.tables), 1)

        tabla = ws.tables["ResumenZonaPaga"]

        self.assertEqual(tabla.ref, "A1:B4")
        self.assertEqual(tabla.tableStyleInfo.name, "TableStyleMedium9")
        self.assertTrue(tabla.tableStyleInfo.showRowStripes)

        # Los datos de la tabla tambien se vacian: son contenido, no formato.
        self.assertIsNone(ws.cell(row=2, column=2).value)

    # -- contenido --------------------------------------------------- #

    def test_los_datos_se_vacian_y_las_cabeceras_no(self):
        """
        Solo sobrevive el texto de las celdas marcadas como cabecera o leyenda.

        Los titulos de la fila 1 deben quedar; los datos de las filas 2..11 no.
        """

        exportado, _ = self._exportar()
        ws = exportado["Datos"]

        for indice, titulo in enumerate(
            ["ID", "Descripcion", "Estado", "Monto", "Fecha"], start=1
        ):
            with self.subTest(cabecera=titulo):
                self.assertEqual(ws.cell(row=1, column=indice).value, titulo)

        for fila in range(2, 12):
            for columna in range(1, 6):
                with self.subTest(fila=fila, columna=columna):
                    self.assertIsNone(
                        ws.cell(row=fila, column=columna).value,
                        f"la celda {ws.cell(row=fila, column=columna).coordinate} "
                        "conservo un dato que deberia haberse vaciado",
                    )

    def test_la_leyenda_se_conserva(self):
        """
        La hoja de leyenda es un bloque chico con relleno de color.

        Su texto es inseparable de su color (cada estado tiene su color), asi
        que se conserva entero.
        """

        exportado, _ = self._exportar()
        leyenda = exportado["Leyenda"]

        self.assertEqual(leyenda["A1"].value, "Estado")
        self.assertEqual(leyenda["A2"].value, "Pendiente")
        # La segunda columna no lleva relleno: sirve para comprobar que el rol
        # se hereda por fila y no se pierde solo por no tener estilo propio.
        self.assertEqual(leyenda["B2"].value, "No ha sido pagada")
        self.assertEqual(leyenda["B3"].value, "Liquidada")
        self.assertEqual(leyenda["B4"].value, "Anulada por el cliente")

    def test_sin_keep_labels_no_queda_ningun_texto(self):
        exportado, _ = self._exportar(
            opciones=ExportOptions(keep_labels=False)
        )

        for nombre in exportado.sheetnames:
            ws = exportado[nombre]
            for fila in ws.iter_rows():
                for celda in fila:
                    with self.subTest(hoja=nombre, celda=celda.coordinate):
                        self.assertIsNone(celda.value)

    # -- filtros y validaciones -------------------------------------- #

    def test_el_autofiltro_guarda_rango_y_criterios_activos(self):
        """
        El filtro tiene valores seleccionados y una fila oculta.

        Los dos van a la base: los criterios en `columns_json` y la fila oculta en
        `hidden_rows_json`.
        """

        version = self.plantilla.current_version
        hoja = version.sheets.get(name="Datos")
        autofiltro = hoja.autofilter

        self.assertEqual(autofiltro.ref, "A1:E11")

        self.assertEqual(len(autofiltro.columns_json), 1)
        columna = autofiltro.columns_json[0]
        self.assertEqual(columna["colId"], "2")
        self.assertEqual(
            sorted(columna["filters"]["vals"]),
            ["Pagada", "Pendiente"],
        )

        self.assertIn(4, autofiltro.hidden_rows_json)
        self.assertIsNotNone(autofiltro.sort_state_json)

    def test_el_autofiltro_se_reexporta_con_sus_criterios(self):
        exportado, _ = self._exportar()
        ws = exportado["Datos"]

        self.assertEqual(ws.auto_filter.ref, "A1:E11")

        self.assertEqual(len(ws.auto_filter.filterColumn), 1)
        # `Filters.filter` es una lista de cadenas, no de objetos con `.val`.
        valores = list(ws.auto_filter.filterColumn[0].filters.filter)
        self.assertEqual(sorted(valores), ["Pagada", "Pendiente"])

    def test_las_filas_ocultas_se_conservan(self):
        exportado, _ = self._exportar()

        self.assertTrue(exportado["Datos"].row_dimensions[4].hidden)

    def test_la_validacion_de_datos_se_conserva(self):
        exportado, _ = self._exportar()
        validaciones = list(exportado["Datos"].data_validations.dataValidation)

        self.assertEqual(len(validaciones), 1)

        validacion = validaciones[0]
        self.assertEqual(validacion.type, "list")
        self.assertEqual(str(validacion.sqref), "C2:C11")
        self.assertIn("Pendiente", validacion.formula1)

    def test_el_formato_condicional_se_conserva_con_su_dxf(self):
        exportado, _ = self._exportar()
        reglas = exportado["Datos"].conditional_formatting

        rangos = [str(r.sqref) for r in reglas]

        self.assertIn("D2:D11", rangos)

        for rango in reglas:
            if str(rango.sqref) == "D2:D11":
                regla = reglas[rango][0]
                self.assertEqual(regla.type, "cellIs")
                self.assertEqual(regla.operator, "greaterThan")
                self.assertIsNotNone(regla.dxf)
                # El dxf es el relleno rojo y la fuente roja oscura.
                self.assertIsNotNone(regla.dxf.fill)
                self.assertIsNotNone(regla.dxf.font)

    def test_los_formatos_numericos_se_conservan(self):
        exportado, _ = self._exportar()
        ws = exportado["Datos"]

        # Columna A en texto plano, D con separador de miles, E como mes-anio.
        self.assertEqual(ws["A2"].number_format, "@")
        self.assertEqual(ws["D2"].number_format, "#,##0.00")
        self.assertEqual(ws["E2"].number_format, "mmm-yy")

    # -- determinismo ------------------------------------------------ #

    def test_capturar_dos_veces_da_los_mismos_hashes_de_estilo(self):
        """
        Los estilos se deduplican por hash: capturar otra vez el mismo formato
        no crea estilos nuevos, aunque el archivo sea distinto.

        El archivo tiene que ser distinto porque `services.capturar` rechaza el
        que ya fue capturado (mismo SHA). Se cambia el nombre de la hoja, que no
        toca ningun estilo, asi que los hashes tienen que ser los mismos.
        """

        segunda = services.capturar(
            self.segunda_ruta, nombre="Plantilla Sintética"
        )

        self.assertEqual(segunda["version"].version_no, 2)
        self.assertNotEqual(
            segunda["version"].source_sha256,
            self.captura["version"].source_sha256,
        )

        # Los estilos son globales y se deduplican por hash: la segunda
        # captura no crea estilos nuevos.
        hashes_primera = set(models.Style.objects.values_list("hash", flat=True))
        total_despues = models.Style.objects.count()

        tercera = services.capturar(
            self.tercera_ruta, nombre="Plantilla Sintética"
        )
        del tercera

        self.assertEqual(models.Style.objects.count(), total_despues)
        self.assertEqual(
            set(models.Style.objects.values_list("hash", flat=True)),
            hashes_primera,
        )

    def test_el_rollback_devuelve_una_version_anterior(self):
        services.capturar(self.segunda_ruta, nombre="Plantilla Sintética")
        self.plantilla.refresh_from_db()
        self.assertEqual(self.plantilla.current_version.version_no, 2)

        services.hacer_rollback(
            self.plantilla, self.captura["version"]
        )
        self.plantilla.refresh_from_db()

        self.assertEqual(self.plantilla.current_version.version_no, 1)
        # El historial sigue entero.
        self.assertEqual(self.plantilla.versions.count(), 2)


# --------------------------------------------------------------------- #
# Archivo de referencia
# --------------------------------------------------------------------- #

@unittest.skipUnless(
    _fixture_disponible(),
    "falta fixtures/ZONA_PAGA_V764_MARTES.XLSX (no se versiona en git)",
)
class TestArchivoDeReferencia(BaseTemporal):
    """
    El caso real: `ZONA_PAGA_V764_MARTES.XLSX`.

    Comprueba lo que el archivo de referencia trae y el archivo sintetico no:
    muchas hojas con espacios en el nombre, dimensiones enormes, formatos
    condicionales con rangos fragmentados y colores de tema con tint.
    """

    def setUp(self):
        super().setUp()
        self.captura = services.capturar(
            RUTA_FIXTURE, nombre=NOMBRE_PLANTILLA
        )
        self.plantilla = self.captura["plantilla"]

    def test_se_capturan_las_cinco_hojas_en_orden(self):
        nombres = [
            hoja.name
            for hoja in self.plantilla.current_version.sheets.order_by("position")
        ]

        self.assertEqual(
            nombres,
            [
                "Version 764",
                "Hoja1",
                "En proceso",
                "Entrada y Salida ZP MTT",
                "Version_DB",
            ],
        )

    def test_el_nombre_de_archivo_se_normaliza_a_xlsx(self):
        self.assertEqual(
            self.plantilla.export_filename, "ZONA_PAGA_V764_MARTES.xlsx"
        )

    def test_el_formato_coincide_celda_por_celda(self):
        import openpyxl

        exportado = services.exportar(self.plantilla)
        salida = self.ruta("exportado.xlsx")
        with open(salida, "wb") as archivo:
            archivo.write(exportado["datos"])

        original = openpyxl.load_workbook(RUTA_FIXTURE)
        generado = openpyxl.load_workbook(salida)
        self.addCleanup(original.close)
        self.addCleanup(generado.close)

        diferencias = comparador.comparar_hojas(original, generado)

        self.assertEqual(
            diferencias,
            [],
            f"{len(diferencias)} diferencias de formato:\n"
            + "\n".join(diferencias[:60]),
        )

    def test_no_queda_ningun_dato_del_original(self):
        """
        Ninguna celda marcada como dato conserva texto.

        Las cabeceras y leyendas si se conservan; lo que se verifica aqui es
        que las filas de datos estan vacias.
        """

        exportado = services.exportar(self.plantilla)
        salida = self.ruta("exportado.xlsx")
        with open(salida, "wb") as archivo:
            archivo.write(exportado["datos"])

        import openpyxl

        generado = openpyxl.load_workbook(salida)
        self.addCleanup(generado.close)

        version = self.plantilla.current_version
        celdas_con_texto = set()
        for etiqueta in models.CellLabel.objects.filter(sheet__version=version):
            celdas_con_texto.add((etiqueta.sheet.name, etiqueta.row_idx, etiqueta.col_idx))

        for nombre in generado.sheetnames:
            ws = generado[nombre]
            for fila in ws.iter_rows():
                for celda in fila:
                    if celda.value is None:
                        continue

                    clave = (nombre, celda.row, celda.column)
                    if clave not in celdas_con_texto:
                        self.fail(
                            f"{nombre}!{celda.coordinate} conservo el valor "
                            f"{celda.value!r}, que no es una cabecera ni una leyenda"
                        )

    def test_la_hoja_de_millon_de_filas_se_procesa_rapido(self):
        """
        `Hoja1` declara mas de un millon de filas.

        El criterio es que no se itere hasta el final: el tiempo tiene que ser
        del orden de segundos y la memoria contenida.
        """

        import time

        inicio = time.monotonic()
        exportado = services.exportar(self.plantilla)
        transcurrido = time.monotonic() - inicio

        self.assertGreater(len(exportado["datos"]), 0)
        self.assertLess(
            transcurrido,
            120,
            f"exportar tardo {transcurrido:.1f}s, demasiado para el tamano del archivo",
        )

    def test_los_tramos_de_estilo_son_menos_que_las_celdas(self):
        """
        El motor guarda estilos por tramos, no por celda.

        Esta es la propiedad que hace viable un archivo grande: si los tramos
        fueran del mismo tamaño que las celdas, el mecanismo no serviria de nada.
        """

        version = self.plantilla.current_version
        tramos = models.CellStyleRun.objects.filter(sheet__version=version).count()

        # Cuantas celdas con estilo hay realmente en el libro.
        import openpyxl

        libro = openpyxl.load_workbook(RUTA_FIXTURE)
        self.addCleanup(libro.close)

        celdas = 0
        for nombre in libro.sheetnames:
            for fila in libro[nombre].iter_rows():
                celdas += sum(
                    1
                    for celda in fila
                    if getattr(celda, "_style", None) and any(celda._style)
                )

        self.assertGreater(celdas, 0)
        self.assertLess(
            tramos,
            celdas,
            f"los tramos ({tramos}) no son menos que las celdas con estilo "
            f"({celdas}): el run-length no esta comprimiendo",
        )


# --------------------------------------------------------------------- #
# Opciones y validacion de entrada
# --------------------------------------------------------------------- #

class TestOpciones(TestCase):
    def test_los_valores_por_defecto_son_los_de_la_plantilla(self):
        opciones = ExportOptions()

        self.assertTrue(opciones.keep_labels)
        self.assertFalse(opciones.keep_formulas)
        self.assertFalse(opciones.keep_comment_text)
        self.assertTrue(opciones.keep_data_validation_lists)
        self.assertEqual(opciones.data_rows_mode, "exact")

    def test_un_modo_de_filas_invalido_se_rechaza(self):
        with self.assertRaises(services.ErrorDePlantilla):
            services.opciones_desde_query({"data_rows_mode": "inventado"})

    def test_un_booleano_invalido_se_rechaza(self):
        with self.assertRaises(services.ErrorDePlantilla):
            services.opciones_desde_query({"keep_labels": "quiza"})

    def test_los_parametros_validos_se_traducen(self):
        opciones = services.opciones_desde_query(
            {
                "keep_labels": "0",
                "keep_comment_text": "1",
                "prototype_repeat": "25",
            }
        )

        self.assertFalse(opciones.keep_labels)
        self.assertTrue(opciones.keep_comment_text)
        self.assertEqual(opciones.prototype_repeat, 25)

    def test_una_opcion_sin_soporte_se_rechaza_en_vez_de_ignorarse(self):
        """
        El motor no reescribe formulas ni replica filas tipo. Aceptar el
        parametro y exportar igual haria creer al que pide que la plantilla
        trae la formula, cuando el archivo sale sin ella.
        """

        with self.assertRaises(services.ErrorDePlantilla) as contexto:
            services.opciones_desde_query({"keep_formulas": "1"})

        self.assertIn("keep_formulas", str(contexto.exception))

    def test_el_modo_prototype_tambien_se_rechaza(self):
        with self.assertRaises(services.ErrorDePlantilla) as contexto:
            services.opciones_desde_query({"data_rows_mode": "prototype"})

        self.assertIn("prototype", str(contexto.exception))

    def test_reclasificar_una_heuristica_desesperada_se_rechaza(self):
        with self.assertRaises(services.ErrorDePlantilla) as contexto:
            services.opciones_desde_query({"unknown_role_as": "header"})

        self.assertIn("unknown_role_as", str(contexto.exception))

    def test_las_opciones_por_defecto_si_se_pueden_normalizar(self):
        opciones = services.opciones_desde_query({})

        self.assertEqual(opciones.data_rows_mode, "exact")
        self.assertEqual(opciones.unknown_role_as, "data")

    def test_normalizar_tambien_rechaza_lo_no_soportado_al_uso_directo(self):
        """
        `normalized` es la ultima linea de defensa: si alguien arma
        `ExportOptions` a mano y salta `opciones_desde_query`, el error sale
        igual.
        """

        with self.assertRaises(OpcionNoSoportada):
            ExportOptions(keep_formulas=True).normalized()


class TestExportSinVersion(TestCase):
    def test_exportar_una_plantilla_sin_version_da_error_claro(self):
        plantilla = models.Template.objects.create(
            name="Sin capturar", export_filename="sin.xlsx"
        )

        with self.assertRaises(services.ErrorDePlantilla) as contexto:
            services.exportar(plantilla)

        self.assertIn("version capturada", str(contexto.exception))

    def test_no_se_puede_capturar_sin_nombre(self):
        with self.assertRaises(services.ErrorDePlantilla):
            services.capturar("cualquiera.xlsx", nombre="   ")

    def test_el_nombre_se_valida_antes_de_leer_el_archivo(self):
        """
        Un nombre vacio con una ruta que no existe tiene que fallar por el
        nombre, no con `FileNotFoundError`: el mensaje del nombre es el que
        dice que corregir.
        """

        with self.assertRaises(services.ErrorDePlantilla) as contexto:
            services.capturar("no-existe.xlsx", nombre="")

        self.assertIn("nombre", str(contexto.exception))


class TestArchivoDuplicado(BaseTemporal):
    """Un archivo identico a uno ya capturado no crea una version mas."""

    def setUp(self):
        super().setUp()
        # `ruta` es un metodo de `BaseTemporal`, asi que la ruta del archivo
        # guardado va en otro atributo: sobrescribir el metodo dejaria al
        # `self.ruta(...)` de las lineas siguientes sin callable.
        self.archivo = self.ruta("dup.xlsx")
        construir_sintetico(self.archivo)

        self.captura = services.capturar(
            self.archivo, nombre="Plantilla Sintética"
        )

    def test_el_mismo_archivo_se_rechaza(self):
        with self.assertRaises(services.ErrorDePlantillaDuplicada) as contexto:
            services.capturar(self.archivo, nombre="Otra plantilla")

        # El mensaje dice donde esta: la accion que sirve es elegir esa.
        self.assertIn("Plantilla Sintética", str(contexto.exception))
        self.assertIn("version 1", str(contexto.exception))

    def test_no_se_crea_ninguna_version(self):
        with self.assertRaises(services.ErrorDePlantillaDuplicada):
            services.capturar(self.archivo, nombre="Plantilla Sintética")

        self.assertEqual(models.TemplateVersion.objects.count(), 1)
        self.assertEqual(models.Template.objects.count(), 1)

    def test_tambien_se_rechaza_sobre_la_misma_plantilla(self):
        with self.assertRaises(services.ErrorDePlantillaDuplicada):
            services.capturar(
                self.archivo, plantilla=self.captura["plantilla"]
            )

        self.assertEqual(
            self.captura["plantilla"].versions.count(), 1
        )

    def test_un_archivo_distinto_si_se_acepta(self):
        otra = self.ruta("otra.xlsx")
        construir_sintetico(otra, hoja_datos="Datos2")

        resultado = services.capturar(otra, nombre="Otra plantilla")

        self.assertEqual(resultado["version"].version_no, 1)
        self.assertTrue(resultado["creada"])
        self.assertEqual(models.Template.objects.count(), 2)

    def test_el_duplicado_es_un_tipo_de_error_de_plantilla(self):
        """La vista distingue el 409 con una clase propia, no por el texto."""

        self.assertTrue(
            issubclass(
                services.ErrorDePlantillaDuplicada, services.ErrorDePlantilla
            )
        )


class TestCapturarConDestino(BaseTemporal):
    """`plantilla=` agrega la version a la plantilla indicada."""

    def setUp(self):
        super().setUp()
        self.archivo = self.ruta("destino.xlsx")
        construir_sintetico(self.archivo)

        self.captura = services.capturar(self.archivo, nombre="Versión Zona Paga")
        self.plantilla = self.captura["plantilla"]
        self.nombre_descarga = self.plantilla.export_filename

    def test_agrega_la_version_a_la_plantilla(self):
        otra = self.ruta("destino-2.xlsx")
        construir_sintetico(otra, hoja_datos="Datos2")

        resultado = services.capturar(otra, plantilla=self.plantilla)

        self.assertEqual(resultado["version"].version_no, 2)
        self.assertFalse(resultado["creada"])
        self.assertEqual(models.Template.objects.count(), 1)

    def test_no_cambia_el_nombre_ni_el_archivo_de_descarga(self):
        """
        El nombre de descarga se decide al crear. Si cambiara en cada captura,
        un enlace ya compartido bajaria otro archivo.
        """

        otra = self.ruta("destino-3.xlsx")
        construir_sintetico(otra, hoja_datos="Datos3")

        services.capturar(otra, plantilla=self.plantilla)
        self.plantilla.refresh_from_db()

        self.assertEqual(self.plantilla.name, "Versión Zona Paga")
        self.assertEqual(self.plantilla.export_filename, self.nombre_descarga)

    def test_el_nombre_que_aparece_en_el_registro_es_el_destino(self):
        otra = self.ruta("destino-4.xlsx")
        construir_sintetico(otra, hoja_datos="Datos4")

        resultado = services.capturar(
            otra, nombre="Nombre que se ignora", plantilla=self.plantilla
        )

        self.assertEqual(resultado["plantilla"].name, "Versión Zona Paga")

    def test_no_exige_nombre_si_hay_destino(self):
        otra = self.ruta("destino-5.xlsx")
        construir_sintetico(otra, hoja_datos="Datos5")

        resultado = services.capturar(otra, plantilla=self.plantilla)

        self.assertEqual(resultado["version"].version_no, 2)

    def test_sin_publicar_no_mueve_la_version_vigente(self):
        otra = self.ruta("destino-6.xlsx")
        construir_sintetico(otra, hoja_datos="Datos6")

        services.capturar(otra, plantilla=self.plantilla, publicar=False)
        self.plantilla.refresh_from_db()

        nueva = self.plantilla.versions.get(version_no=2)

        self.assertEqual(nueva.status, models.TemplateVersion.Status.BORRADOR)
        self.assertEqual(self.plantilla.current_version.version_no, 1)
        # La anterior no se archiva sola: queda vigente hasta que se publique
        # otra.
        self.assertEqual(
            self.plantilla.versions.get(version_no=1).status,
            models.TemplateVersion.Status.VIGENTE,
        )
