"""
Generador de Excel sinteticos para probar el motor.

El archivo de referencia del proyecto (`fixtures/ZONA_PAGA_V764_MARTES.XLSX`)
cubre el caso real, pero para demostrar que el motor es generico hace falta un
segundo archivo con caracteristicas *distintas*: celdas combinadas, validacion
de datos, tabla, autofiltro con criterios activos y filas ocultas, color de
pestana, panel inmovilizado y formatos condicionales de otro tipo.

Se construye con openpyxl y despues se reescribe el XML a mano para las partes
que openpyxl no expone (criterios activos del filtro, filas ocultas). Asi el
test no depende de que openpyxl sepa escribir lo que el motor debe leer.
"""

import os
import zipfile
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Color, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo


def construir(ruta, hoja_datos="Datos", hoja_leyenda="Leyenda",
              hoja_tabla="Resumen"):
    """
    Crea un `.xlsx` pequeno con caracteristicas que el archivo real no tiene.

    Devuelve la ruta escrita.
    """

    libro = Workbook()

    # ---- hoja de datos ------------------------------------------- #
    ws = libro.active
    ws.title = hoja_datos

    # Anchos de columna distintos entre si.
    ws.column_dimensions["A"].width = 12.5
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 22

    # Alturas de fila: la 1 es la cabecera y va mas alta que el resto.
    ws.row_dimensions[1].height = 32.5
    ws.row_dimensions[2].height = 15.75

    encabezados = ["ID", "Descripcion", "Estado", "Monto", "Fecha"]

    # Estilo de la cabecera: negrita, relleno, centrado y wrap.
    #
    # El relleno va con `Color(theme=4, tint=-0.0999)` a proposito: es un color
    # de tema, no un RGB. El motor tiene que conservarlo con su tint y no
    # resolverlo, y este archivo es lo que lo comprueba.
    color_tema = Color(theme=4, tint=-0.099977)

    estilo_cabecera = {
        "font": Font(name="Calibri", size=11, bold=True, color=Color(rgb="FFFFFFFF")),
        "fill": PatternFill(
            patternType="solid", fgColor=color_tema, bgColor=color_tema
        ),
        "alignment": Alignment(horizontal="center", vertical="center", wrap_text=True),
        "border": Border(
            left=Side(style="thin", color=Color(rgb="FF44546A")),
            right=Side(style="thin", color=Color(rgb="FF44546A")),
            top=Side(style="thin", color=Color(rgb="FF44546A")),
            bottom=Side(style="thin", color=Color(rgb="FF44546A")),
        ),
    }

    for indice, titulo in enumerate(encabezados, start=1):
        celda = ws.cell(row=1, column=indice)
        celda.value = titulo
        for atributo, valor in estilo_cabecera.items():
            setattr(celda, atributo, valor)

    # La combinacion va en una fila aparte, y no sobre la cabecera: al
    # combinar, la celda de la derecha pasa a ser `MergedCell` y pierde su
    # valor, asi que combinar sobre el encabezado dejaria una columna sin
    # titulo y el motor no tendria nada que conservar.
    celda_titulo = ws.cell(row=13, column=1, value="Resumen del periodo")
    for atributo, valor in estilo_cabecera.items():
        setattr(celda_titulo, atributo, valor)
    ws.merge_cells("A13:C13")

    # Formato de fecha en la columna E, para comprobar el `number_format`.
    formato_fecha = "mmm-yy"
    formato_texto = "@"

    estados = ["Pendiente", "Pagada", "Cancelada"]

    for fila in range(2, 12):
        ws.cell(row=fila, column=1, value=fila - 1).number_format = formato_texto
        ws.cell(row=fila, column=2, value=f"Fila de prueba {fila - 1}")
        ws.cell(
            row=fila, column=3, value=estados[(fila - 2) % len(estados)]
        ).number_format = formato_texto
        ws.cell(row=fila, column=4, value=100 * fila).number_format = "#,##0.00"
        ws.cell(row=fila, column=5, value="2026-03-15").number_format = formato_fecha

    # Validacion de datos: lista desplegable con valores literales.
    validacion = DataValidation(
        type="list",
        formula1='"Pendiente,Pagada,Cancelada"',
        allow_blank=True,
    )
    ws.add_data_validation(validacion)
    validacion.add("C2:C11")

    # Formato condicional: celda mayor que 500 en rojo.
    ws.conditional_formatting.add(
        "D2:D11",
        CellIsRule(
            operator="greaterThan",
            formula=["500"],
            fill=PatternFill(patternType="solid", fgColor="FFFFC7CE"),
            font=Font(color="FF9C0006"),
        ),
    )

    # Panel inmovilizado y color de pestana.
    ws.freeze_panes = "A2"
    ws.sheet_properties.tabColor = "FF00B050"

    # Ocultar una fila: el autofiltro activo la declara oculta.
    ws.row_dimensions[4].hidden = True

    # ---- hoja con tabla ------------------------------------------- #
    # Va en su propia hoja a proposito: Excel no admite un autofiltro y una
    # tabla sobre el mismo rango, y el archivo de datos ya usa el autofiltro.
    resumen = libro.create_sheet(hoja_tabla)
    # Una tabla de Excel necesita fila de encabezados: sin ella, openpyxl avisa
    # que el archivo no sera legible.
    resumen["A1"] = "Concepto"
    resumen["B1"] = "Importe"
    for celda in ("A1", "B1"):
        resumen[celda].font = Font(bold=True)

    for fila, (concepto, valor) in enumerate(
        [
            ("Total", 1250.5),
            ("Pagadas", 830.25),
            ("Anuladas", 420.25),
        ],
        start=2,
    ):
        resumen.cell(row=fila, column=1, value=concepto)
        resumen.cell(row=fila, column=2, value=valor).number_format = "#,##0.00"

    tabla = Table(displayName="ResumenZonaPaga", ref="A1:B4")
    tabla.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    resumen.add_table(tabla)

    # ---- hoja de leyenda ------------------------------------------ #
    leyenda = libro.create_sheet(hoja_leyenda)
    leyenda["A1"] = "Estado"
    leyenda["B1"] = "Significado"

    for celda in ("A1", "B1"):
        leyenda[celda].font = Font(bold=True)
        leyenda[celda].fill = PatternFill(patternType="solid", fgColor="FF95B3D7")
        leyenda[celda].alignment = Alignment(horizontal="center")

    pares = [
        ("Pendiente", "No ha sido pagada"),
        ("Pagada", "Liquidada"),
        ("Cancelada", "Anulada por el cliente"),
    ]

    for indice, (estado, significado) in enumerate(pares, start=2):
        leyenda.cell(row=indice, column=1, value=estado).fill = PatternFill(
            patternType="solid",
            fgColor={"Pendiente": "FFFFFF99", "Pagada": "FF00B0F0", "Cancelada": "FFFF0000"}[estado],
        )
        leyenda.cell(row=indice, column=2, value=significado)

    # Tercer formato numerico: texto plano, para que el motor lo conserve.
    leyenda["B2"].number_format = "@"

    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    libro.save(ruta)

    _reescribir_theme(ruta)
    _reescribir_autofiltro(ruta, hoja_datos)

    return ruta


def _reescribir_autofiltro(ruta, nombre_hoja):
    """
    Anade un autofiltro con criterios activos y filas ocultas al XML.

    openpyxl sabe escribir un `autoFilter` con rango pero no los
    `filterColumn` con valores, asi que el nodo se inyecta a mano en el XML de
    la hoja. El archivo se reescribe completo porque el ZIP no admite
    reemplazar una entrada sin rearmarlo.
    """

    import re
    import shutil

    with zipfile.ZipFile(ruta, "r") as origen:
        entradas = {nombre: origen.read(nombre) for nombre in origen.namelist()}

    # Descubre el nombre real de la parte de la hoja.
    ruta_hoja = None
    for nombre in entradas:
        if nombre.startswith("xl/worksheets/sheet") and nombre.endswith(".xml"):
            ruta_hoja = nombre
            break

    if ruta_hoja is None:
        return

    xml = entradas[ruta_hoja].decode("utf-8")

    # El rango del filtro: la cabecera y las 10 filas de datos.
    auto_filter = (
        '<autoFilter ref="A1:E11">'
        '<filterColumn colId="2">'
        '<filters>'
        '<filter val="Pendiente"/>'
        '<filter val="Pagada"/>'
        "</filters>"
        "</filterColumn>"
        '<sortState ref="A2:E11">'
        '<sortCondition ref="A2:A11"/>'
        "</sortState>"
        "</autoFilter>"
    )

    # `autoFilter` va justo despues de `</sheetData>` si no existe todavia.
    if "<autoFilter" in xml:
        xml = re.sub(
            r"<autoFilter[^>]*>.*?</autoFilter>|<autoFilter[^>]*/>",
            auto_filter,
            xml,
            flags=re.DOTALL,
        )
    else:
        xml = xml.replace("</sheetData>", "</sheetData>" + auto_filter, 1)

    entradas[ruta_hoja] = xml.encode("utf-8")

    temporal = ruta + ".tmp"
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as destino:
        for nombre, datos in entradas.items():
            destino.writestr(nombre, datos)

    shutil.move(temporal, ruta)


def _reescribir_theme(ruta):
    """
    Cambia el theme del libro por uno reconocible.

    El archivo que genera openpyxl trae su theme de fábrica. Como el motor
    conserva los colores como `theme=N` en vez de resolverlos a RGB, la unica
    forma de que la plantilla exportada se vea igual es reinyectar el theme
    original. Para que el test pueda distinguir "se reinyecto" de "ha salido
    igual por casualidad", el theme de aqui tiene que ser distinto del de
    fábrica.
    """

    import shutil

    with zipfile.ZipFile(ruta, "r") as origen:
        entradas = {nombre: origen.read(nombre) for nombre in origen.namelist()}

    nombre_theme = "xl/theme/theme1.xml"
    if nombre_theme not in entradas:
        return

    xml = entradas[nombre_theme].decode("utf-8")
    xml = xml.replace('name="Office Theme"', 'name="Tema Zona Paga"', 1)
    # Un color de acento distinto: si el motor resolveda indices de tema, la
    # diferencia se veria en el relleno de la cabecera.
    xml = xml.replace('<a:accent1><a:srgbClr val="4F81BD"/></a:accent1>',
                      '<a:accent1><a:srgbClr val="C00000"/></a:accent1>', 1)

    entradas[nombre_theme] = xml.encode("utf-8")

    temporal = ruta + ".tmp"
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as destino:
        for nombre, datos in entradas.items():
            destino.writestr(nombre, datos)

    shutil.move(temporal, ruta)


__all__ = ["construir", "escape"]