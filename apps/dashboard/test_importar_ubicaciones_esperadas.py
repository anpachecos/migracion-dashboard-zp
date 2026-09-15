from datetime import datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
from django.test import SimpleTestCase

from apps.dashboard.repositories import ubicaciones_repository
from apps.dashboard.management.commands.importar_ubicaciones_esperadas import (
    LATITUD_LABORATORIO_ZP,
    LONGITUD_LABORATORIO_ZP,
    NOMBRE_LABORATORIO_ZP,
    RADIO_LABORATORIO_ZP,
    Command,
)


class ImportarUbicacionesEsperadasCaracterizacionTests(SimpleTestCase):
    FECHA_CARGA = datetime(2026, 9, 10, 12, 0)

    def setUp(self):
        self.stdout = StringIO()
        self.stderr = StringIO()
        self.comando = Command(stdout=self.stdout, stderr=self.stderr)

    def fila_valida(self, operativa="SI", **cambios):
        fila = {
            "IDDS": 7500001,
            "Nombre": "Zona sintética",
            "Serie Val": "SERIE-TEST",
            "Latitud": -33.45,
            "Longitud": -70.66,
            "Operativa": operativa,
            "Radio": 150,
        }
        fila.update(cambios)
        return fila

    def crear_excel(self, directorio, filas, nombre="ZONA PAGA V755.xlsx", hoja="Version_DB"):
        ruta = Path(directorio) / nombre
        pd.DataFrame(filas).to_excel(ruta, sheet_name=hoja, index=False)
        return ruta

    def conexion_falsa(self):
        cursor = MagicMock(name="cursor_oracle_falso")
        conexion = MagicMock(name="conexion_oracle_falsa")
        conexion.cursor.return_value.__enter__.return_value = cursor
        contexto = MagicMock(name="contexto_conexion_falsa")
        contexto.__enter__.return_value = conexion
        return contexto, conexion, cursor

    def referencia_laboratorio(self):
        return {
            "NOMBRE": NOMBRE_LABORATORIO_ZP,
            "LATITUD_ESPERADA": LATITUD_LABORATORIO_ZP,
            "LONGITUD_ESPERADA": LONGITUD_LABORATORIO_ZP,
            "RADIO_METROS": RADIO_LABORATORIO_ZP,
            "OPERATIVA": 0,
            "ORIGEN_UBICACION": "laboratorio_default",
        }

    def ejecutar_importacion_controlada(self, ruta, error_upsert=None):
        contexto, conexion, cursor = self.conexion_falsa()

        with patch(
            "apps.dashboard.repositories.ubicaciones_repository.obtener_conexion_oracle",
            return_value=contexto,
        ) as mock_obtener_conexion, patch(
            "apps.dashboard.repositories.ubicaciones_repository.existe_vigente",
            return_value=False,
        ), patch(
            "apps.dashboard.repositories.ubicaciones_repository.upsert_vigente",
            side_effect=error_upsert,
        ) as mock_upsert, patch(
            "apps.dashboard.repositories.ubicaciones_repository.actualizar_historial",
            return_value="nuevo",
        ), patch(
            "apps.dashboard.repositories.ubicaciones_repository."
            "mover_ausentes_a_laboratorio",
            return_value=(0, 0, 0),
        ), patch(
            "apps.dashboard.management.commands.importar_ubicaciones_esperadas.registrar_log_importacion"
        ) as mock_log, patch.object(
            self.comando, "ahora_oracle", return_value=self.FECHA_CARGA
        ):
            self.comando.handle(ruta_excel=str(ruta))

        self.mock_upsert = mock_upsert
        return mock_obtener_conexion, mock_log, conexion, cursor

    def test_archivo_inexistente_registra_error_y_no_conecta_oracle(self):
        ruta = Path("archivo-sintetico-inexistente-V755.xlsx")
        with patch(
            "apps.dashboard.repositories.ubicaciones_repository.obtener_conexion_oracle"
        ) as mock_conexion, patch(
            "apps.dashboard.management.commands.importar_ubicaciones_esperadas.registrar_log_importacion"
        ) as mock_log:
            self.comando.handle(ruta_excel=str(ruta))

        mock_conexion.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("No se encontró el archivo", self.stderr.getvalue())

    def test_excel_sin_hoja_version_db_se_rechaza_sin_oracle(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio, [self.fila_valida()], hoja="OtraHoja")
            with patch(
                "apps.dashboard.repositories.ubicaciones_repository.obtener_conexion_oracle"
            ) as mock_conexion, patch(
                "apps.dashboard.management.commands.importar_ubicaciones_esperadas.registrar_log_importacion"
            ) as mock_log:
                self.comando.handle(ruta_excel=str(ruta))

        mock_conexion.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("No se encontró la hoja Version_DB", self.stderr.getvalue())

    def test_excel_sin_columnas_requeridas_llega_a_fake_oracle_y_omite_fila(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio, [{"Columna ajena": "dato"}])
            mock_conexion, mock_log, conexion, _ = self.ejecutar_importacion_controlada(ruta)

        mock_conexion.assert_called_once()
        self.mock_upsert.assert_not_called()
        conexion.commit.assert_called_once()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "OK")
        self.assertIn("Omitidos: 1", mock_log.call_args.kwargs["mensaje"])

    def test_version_se_extrae_desde_nombre_archivo(self):
        casos = {
            "ZONA PAGA V755.xlsx": "V755",
            "zona paga v 812 jueves.xlsx": "V812",
            "sin-version.xlsx": None,
        }
        for nombre, esperado in casos.items():
            with self.subTest(nombre=nombre):
                self.assertEqual(self.comando.extraer_version_desde_nombre(nombre), esperado)

    def test_encabezados_normalizan_tildes_simbolos_y_formato(self):
        dataframe = pd.DataFrame(columns=[
            "  CÓDIGO-ZP/TS ", "Serie.Val", "N° Val", "Horario Sábado",
            "Inicio_Operación", "LATITUD", "Longitud", "OPERATIVA", "Radio",
            "IDDS", "Nombre",
        ])

        normalizado = self.comando.normalizar_dataframe(dataframe)

        for columna in (
            "CODIGO_ZP_TS", "SERIE_VALIDADOR", "NUM_VAL", "HORARIO_SABADO",
            "INICIO_OPERACION", "LATITUD_ESPERADA", "LONGITUD_ESPERADA",
            "OPERATIVA", "RADIO_METROS", "IDDS", "NOMBRE",
        ):
            self.assertIn(columna, normalizado.columns)

    def test_operativa_si_y_si_con_tilde_conservan_datos_excel(self):
        for operativa in ("SI", "SÍ"):
            with self.subTest(operativa=operativa):
                datos = self.comando.normalizar_fila(
                    pd.Series(self.comando.normalizar_dataframe(
                        pd.DataFrame([self.fila_valida(operativa)])
                    ).iloc[0]),
                    self.FECHA_CARGA,
                    "ZONA PAGA V755.xlsx",
                    "V755",
                )
                self.assertEqual(datos["NOMBRE"], "Zona sintética")
                self.assertEqual(datos["LATITUD_ESPERADA"], -33.45)
                self.assertEqual(datos["LONGITUD_ESPERADA"], -70.66)
                self.assertEqual(datos["RADIO_METROS"], 150.0)
                self.assertEqual(datos["OPERATIVA"], 1)
                self.assertEqual(datos["ORIGEN_UBICACION"], "excel")

    def test_operativa_no_usa_referencia_laboratorio(self):
        fila = self.comando.normalizar_dataframe(pd.DataFrame([
            self.fila_valida("NO")
        ])).iloc[0]
        datos = self.comando.normalizar_fila(
            fila, self.FECHA_CARGA, "ZONA PAGA V755.xlsx", "V755"
        )

        self.assertEqual(datos["NOMBRE"], NOMBRE_LABORATORIO_ZP)
        self.assertEqual(datos["LATITUD_ESPERADA"], LATITUD_LABORATORIO_ZP)
        self.assertEqual(datos["LONGITUD_ESPERADA"], LONGITUD_LABORATORIO_ZP)
        self.assertEqual(datos["RADIO_METROS"], RADIO_LABORATORIO_ZP)
        self.assertEqual(datos["OPERATIVA"], 0)
        self.assertEqual(datos["ORIGEN_UBICACION"], "laboratorio")

    def test_operatividad_invalida_omite_fila(self):
        fila = self.comando.normalizar_dataframe(pd.DataFrame([
            self.fila_valida("QUIZÁS")
        ])).iloc[0]
        self.assertIsNone(self.comando.normalizar_fila(
            fila, self.FECHA_CARGA, "archivo.xlsx", None
        ))

    def test_fila_sin_amid_se_omite(self):
        fila = self.comando.normalizar_dataframe(pd.DataFrame([
            self.fila_valida(IDDS=None)
        ])).iloc[0]
        self.assertIsNone(self.comando.normalizar_fila(
            fila, self.FECHA_CARGA, "archivo.xlsx", None
        ))

    def test_operativa_si_sin_coordenadas_o_radio_validos_se_omite(self):
        for campo in ("Latitud", "Longitud", "Radio"):
            with self.subTest(campo=campo):
                fila = self.comando.normalizar_dataframe(pd.DataFrame([
                    self.fila_valida(**{campo: "inválido"})
                ])).iloc[0]
                self.assertIsNone(self.comando.normalizar_fila(
                    fila, self.FECHA_CARGA, "archivo.xlsx", None
                ))

    def test_amid_nuevo_crea_historial(self):
        cursor = MagicMock()
        datos = {"AMID": "7500001"}

        with patch.object(
            ubicaciones_repository,
            "obtener_historial_vigente",
            return_value=None,
        ), patch.object(
            ubicaciones_repository,
            "crear_historial",
        ) as mock_crear:
            resultado = ubicaciones_repository.actualizar_historial(
                cursor,
                datos,
                self.FECHA_CARGA,
            )

        self.assertEqual(resultado, "nuevo")
        mock_crear.assert_called_once_with(cursor, datos, self.FECHA_CARGA)

    def test_historial_igual_no_genera_otro_registro(self):
        datos = {
            "AMID": "7500001", "NOMBRE": "Zona", "SERIE_VALIDADOR": "SERIE",
            "LATITUD_ESPERADA": -33.45, "LONGITUD_ESPERADA": -70.66,
            "RADIO_METROS": 150, "OPERATIVA": 1,
            "ORIGEN_UBICACION": "excel", "VERSION_ZP": "V755",
        }
        historial = dict(datos, ID=9)
        cursor = MagicMock()
        with patch.object(
            ubicaciones_repository,
            "obtener_historial_vigente",
            return_value=historial,
        ), patch.object(
            ubicaciones_repository,
            "crear_historial",
        ) as mock_crear:
            resultado = ubicaciones_repository.actualizar_historial(
                cursor,
                datos,
                self.FECHA_CARGA,
            )

        self.assertEqual(resultado, "sin_cambios")
        mock_crear.assert_not_called()
        self.assertFalse(any("UPDATE" in call.args[0] for call in cursor.execute.call_args_list))

    def test_cambio_relevante_cierra_vigencia_y_crea_nueva(self):
        datos = {
            "AMID": "7500001", "NOMBRE": "Zona nueva", "SERIE_VALIDADOR": "SERIE",
            "LATITUD_ESPERADA": -33.45, "LONGITUD_ESPERADA": -70.66,
            "RADIO_METROS": 150, "OPERATIVA": 1,
            "ORIGEN_UBICACION": "excel", "VERSION_ZP": "V755",
        }
        historial = dict(datos, ID=9, NOMBRE="Zona anterior")
        cursor = MagicMock()
        with patch.object(
            ubicaciones_repository,
            "obtener_historial_vigente",
            return_value=historial,
        ), patch.object(
            ubicaciones_repository,
            "crear_historial",
        ) as mock_crear:
            resultado = ubicaciones_repository.actualizar_historial(
                cursor,
                datos,
                self.FECHA_CARGA,
            )

        self.assertEqual(resultado, "cerrado_y_nuevo")
        self.assertIn("UPDATE USR_LAB.HISTORIAL_UBICACION_ESPERADA", cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1]["id"], 9)
        mock_crear.assert_called_once_with(cursor, datos, self.FECHA_CARGA)

    def test_comparacion_numerica_redondea_a_siete_decimales(self):
        self.assertTrue(ubicaciones_repository.numero_igual(1.123456741, 1.123456749))
        self.assertFalse(ubicaciones_repository.numero_igual(1.12345674, 1.12345686))

    def test_amid_activo_ausente_se_mueve_a_laboratorio(self):
        cursor = MagicMock()
        cursor.description = [("AMID",), ("SERIE_VALIDADOR",)]
        cursor.fetchall.return_value = [("7500002", "SERIE-2")]
        with patch.object(
            ubicaciones_repository,
            "obtener_historial_vigente",
            return_value=None,
        ), patch.object(
            ubicaciones_repository,
            "upsert_vigente",
        ) as mock_upsert, patch.object(
            ubicaciones_repository,
            "crear_historial",
        ):
            resultado = ubicaciones_repository.mover_ausentes_a_laboratorio(
                cursor,
                {"7500001"},
                self.FECHA_CARGA,
                "archivo.xlsx",
                "V755",
                self.referencia_laboratorio(),
            )

        datos = mock_upsert.call_args.args[1]
        self.assertEqual(datos["AMID"], "7500002")
        self.assertEqual(datos["NOMBRE"], NOMBRE_LABORATORIO_ZP)
        self.assertEqual(resultado, (1, 0, 1))

    def test_amid_ya_en_laboratorio_no_se_reescribe(self):
        cursor = MagicMock()
        cursor.description = [("AMID",), ("SERIE_VALIDADOR",)]
        cursor.fetchall.return_value = [("7500002", "SERIE-2")]
        with patch.object(
            ubicaciones_repository,
            "obtener_historial_vigente",
            return_value={
                "ID": 5,
                "NOMBRE": NOMBRE_LABORATORIO_ZP,
                "LATITUD_ESPERADA": LATITUD_LABORATORIO_ZP,
                "LONGITUD_ESPERADA": LONGITUD_LABORATORIO_ZP,
                "RADIO_METROS": RADIO_LABORATORIO_ZP,
                "OPERATIVA": 0,
            },
        ), patch.object(
            ubicaciones_repository,
            "upsert_vigente",
        ) as mock_upsert, patch.object(
            ubicaciones_repository,
            "crear_historial",
        ) as mock_crear:
            resultado = ubicaciones_repository.mover_ausentes_a_laboratorio(
                cursor,
                set(),
                self.FECHA_CARGA,
                "archivo.xlsx",
                "V755",
                self.referencia_laboratorio(),
            )

        self.assertEqual(resultado, (0, 0, 0))
        mock_upsert.assert_not_called()
        mock_crear.assert_not_called()

    def test_importacion_exitosa_ejecuta_commit_y_log_ok(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio, [self.fila_valida()])
            _, mock_log, conexion, _ = self.ejecutar_importacion_controlada(ruta)

        conexion.commit.assert_called_once_with()
        conexion.rollback.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "OK")
        self.assertIn("Importación completada en Oracle", self.stdout.getvalue())

    def test_error_oracle_no_confirma_ni_hace_rollback_explicito_y_registra_error(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio, [self.fila_valida()])
            _, mock_log, conexion, _ = self.ejecutar_importacion_controlada(
                ruta, error_upsert=RuntimeError("fallo Oracle sintético")
            )

        conexion.commit.assert_not_called()
        conexion.rollback.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("Error importando ubicaciones a Oracle", self.stderr.getvalue())
        self.assertIn("fallo Oracle sintético", self.stderr.getvalue())
