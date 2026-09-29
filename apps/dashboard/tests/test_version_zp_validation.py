from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from apps.dashboard.services.version_zp_validation import (
    VersionZPValidationError,
    validar_archivo_version_zp,
    validar_upload_basico,
)


class VersionZPValidationTests(SimpleTestCase):
    def fila_valida(self, **cambios):
        fila = {
            "Nombre": "Zona sintética",
            "IDDS": 7500001,
            "Operativa": "SI",
            "Latitud": -33.45,
            "Longitud": -70.66,
            "Radio": 150,
        }
        fila.update(cambios)
        return fila

    def crear_excel(
        self,
        directorio,
        filas=None,
        nombre="Version_DB.xlsx",
        hoja="Version_DB",
        columnas=None,
    ):
        ruta = Path(directorio) / nombre
        dataframe = pd.DataFrame(
            [self.fila_valida()] if filas is None else filas,
            columns=columnas,
        )
        dataframe.to_excel(ruta, sheet_name=hoja, index=False)
        return ruta

    def test_defaults_operativos_versionados(self):
        self.assertEqual(settings.VERSION_ZP_MAX_FILE_BYTES, 5 * 1024 * 1024)
        self.assertEqual(
            settings.VERSION_ZP_MAX_UNCOMPRESSED_BYTES,
            50 * 1024 * 1024,
        )
        self.assertEqual(settings.VERSION_ZP_MAX_ROWS, 5000)
        self.assertEqual(settings.VERSION_ZP_MAX_COLUMNS, 100)
        self.assertEqual(settings.VERSION_ZP_MAX_COMPRESSION_RATIO, 100)

    def test_xlsx_valido_retorna_dimensiones(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio)
            info = validar_archivo_version_zp(ruta)

        self.assertEqual(info.filas, 1)
        self.assertEqual(info.columnas, 6)
        self.assertGreater(info.tamano_comprimido, 0)
        self.assertGreater(info.tamano_descomprimido, info.tamano_comprimido)

    def test_extension_xlsx_es_case_insensitive(self):
        validar_upload_basico("VERSION_DB.XLSX", 1)

    def test_extensiones_no_soportadas_se_rechazan(self):
        for nombre in (
            "Version_DB.xls",
            "Version_DB.txt",
            "Version_DB.csv",
            "Version_DB.xlsm",
        ):
            with self.subTest(nombre=nombre), self.assertRaisesRegex(
                VersionZPValidationError,
                "Formato no soportado",
            ):
                validar_upload_basico(nombre, 1)

    def test_xlsx_valido_renombrado_como_xls_se_rechaza(self):
        with TemporaryDirectory() as directorio:
            ruta_xlsx = self.crear_excel(directorio)
            ruta_xls = ruta_xlsx.with_suffix(".xls")
            ruta_xlsx.rename(ruta_xls)

            with self.assertRaisesRegex(
                VersionZPValidationError,
                "Formato no soportado",
            ):
                validar_archivo_version_zp(ruta_xls)

    def test_archivo_no_zip_se_rechaza(self):
        with TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "Version_DB.xlsx"
            ruta.write_bytes(b"contenido que no es ZIP")
            with self.assertRaisesRegex(
                VersionZPValidationError,
                "no es un contenedor XLSX válido",
            ):
                validar_archivo_version_zp(ruta)

    def test_zip_que_no_es_xlsx_se_rechaza(self):
        with TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "Version_DB.xlsx"
            with ZipFile(ruta, "w", ZIP_DEFLATED) as archivo:
                archivo.writestr("documento.txt", "contenido")

            with self.assertRaisesRegex(
                VersionZPValidationError,
                "no contiene una estructura XLSX válida",
            ):
                validar_archivo_version_zp(ruta)

    def test_xlsx_con_estructura_corrupta_se_rechaza_como_workbook(self):
        with TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "Version_DB.xlsx"
            with ZipFile(ruta, "w", ZIP_DEFLATED) as archivo:
                for nombre in (
                    "[Content_Types].xml",
                    "_rels/.rels",
                    "xl/workbook.xml",
                    "xl/_rels/workbook.xml.rels",
                    "xl/worksheets/sheet1.xml",
                ):
                    archivo.writestr(nombre, "<xml-invalido")

            with self.assertRaisesRegex(
                VersionZPValidationError,
                "corrupto o no es un workbook válido",
            ):
                validar_archivo_version_zp(ruta)

    def test_nombre_version_db_es_exacto(self):
        for hoja in ("version_db", "VERSION_DB", " Version_DB "):
            with self.subTest(hoja=hoja), TemporaryDirectory() as directorio:
                ruta = self.crear_excel(directorio, hoja=hoja)
                with self.assertRaisesRegex(
                    VersionZPValidationError,
                    "No se encontró la hoja Version_DB",
                ):
                    validar_archivo_version_zp(ruta)

    def test_version_db_vacia_se_rechaza(self):
        columnas = ["Nombre", "IDDS", "Operativa", "Latitud", "Longitud", "Radio"]
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(
                directorio,
                filas=[],
                columnas=columnas,
            )
            with self.assertRaisesRegex(
                VersionZPValidationError,
                "no contiene filas de datos",
            ):
                validar_archivo_version_zp(ruta)

    def test_columna_obligatoria_faltante_se_rechaza(self):
        fila = self.fila_valida()
        del fila["Nombre"]
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio, filas=[fila])
            with self.assertRaisesRegex(
                VersionZPValidationError,
                "NOMBRE",
            ):
                validar_archivo_version_zp(ruta)

    def test_columna_adicional_se_permite(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(
                directorio,
                filas=[self.fila_valida(FechaCaptura="2026-09-16")],
            )
            info = validar_archivo_version_zp(ruta)

        self.assertEqual(info.columnas, 7)

    def test_serie_validador_es_opcional(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio)
            info = validar_archivo_version_zp(ruta)

        self.assertEqual(info.filas, 1)

    @override_settings(VERSION_ZP_MAX_FILE_BYTES=10)
    def test_tamano_comprimido_excedido_se_rechaza(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio)
            with self.assertRaisesRegex(
                VersionZPValidationError,
                "tamaño máximo comprimido",
            ):
                validar_archivo_version_zp(ruta)

    @override_settings(VERSION_ZP_MAX_UNCOMPRESSED_BYTES=10)
    def test_tamano_expandido_excedido_se_rechaza(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio)
            with self.assertRaisesRegex(
                VersionZPValidationError,
                "tamaño descomprimido",
            ):
                validar_archivo_version_zp(ruta)

    @override_settings(VERSION_ZP_MAX_COMPRESSION_RATIO=1)
    def test_ratio_compresion_excedido_se_rechaza(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio)
            with self.assertRaisesRegex(
                VersionZPValidationError,
                "relación máxima de compresión",
            ):
                validar_archivo_version_zp(ruta)

    @override_settings(VERSION_ZP_MAX_ROWS=1)
    def test_limite_filas_se_puede_reducir_con_override_settings(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(
                directorio,
                filas=[self.fila_valida(), self.fila_valida(IDDS=7500002)],
            )
            with self.assertRaisesRegex(
                VersionZPValidationError,
                "máximo de filas",
            ):
                validar_archivo_version_zp(ruta)

    @override_settings(VERSION_ZP_MAX_COLUMNS=5)
    def test_limite_columnas_se_puede_reducir_con_override_settings(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio)
            with self.assertRaisesRegex(
                VersionZPValidationError,
                "máximo de columnas",
            ):
                validar_archivo_version_zp(ruta)

    def test_override_settings_modifica_realmente_limite(self):
        with self.settings(VERSION_ZP_MAX_FILE_BYTES=3):
            with self.assertRaises(VersionZPValidationError):
                validar_upload_basico("Version_DB.xlsx", 4)

        validar_upload_basico("Version_DB.xlsx", 4)
