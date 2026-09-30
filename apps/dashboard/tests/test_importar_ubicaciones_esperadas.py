from datetime import datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.dashboard.repositories import ubicaciones_repository
from apps.dashboard.management.commands.importar_ubicaciones_esperadas import (
    LATITUD_LABORATORIO_ZP,
    LONGITUD_LABORATORIO_ZP,
    NOMBRE_LABORATORIO_ZP,
    RADIO_LABORATORIO_ZP,
    Command,
)
from apps.dashboard.services.ubicaciones_dataset_validation import (
    validar_dataset_ubicaciones,
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

    def validar_dataframe(self, dataframe):
        normalizado = self.comando.normalizar_dataframe(dataframe)
        filas = [
            self.comando.adaptar_fila_dataframe(
                fila,
                numero,
                self.FECHA_CARGA,
                "ZONA PAGA V755.xlsx",
                "V755",
            )
            for numero, (_, fila) in enumerate(normalizado.iterrows(), start=2)
        ]
        return validar_dataset_ubicaciones(filas, self.referencia_laboratorio())

    def ejecutar_importacion_controlada(
        self,
        ruta,
        error_upsert=None,
        esperar_error=False,
    ):
        contexto, conexion, cursor = self.conexion_falsa()

        with patch(
            "apps.dashboard.services.oracle_connection.obtener_conexion_oracle",
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
            if esperar_error:
                with self.assertRaises(CommandError):
                    self.comando.handle(ruta_excel=str(ruta))
            else:
                self.comando.handle(ruta_excel=str(ruta))

        self.mock_upsert = mock_upsert
        return mock_obtener_conexion, mock_log, conexion, cursor

    def test_archivo_inexistente_registra_error_y_no_conecta_oracle(self):
        ruta = Path("archivo-sintetico-inexistente-V755.xlsx")
        with patch(
            "apps.dashboard.services.oracle_connection.obtener_conexion_oracle"
        ) as mock_conexion, patch(
            "apps.dashboard.management.commands.importar_ubicaciones_esperadas.registrar_log_importacion"
        ) as mock_log:
            with self.assertRaisesRegex(CommandError, "No se encontró el archivo"):
                self.comando.handle(ruta_excel=str(ruta))

        mock_conexion.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("No se encontró el archivo", self.stderr.getvalue())

    def test_cli_rechaza_extension_antes_de_pandas_y_repository(self):
        with TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "ZONA PAGA V755.xls"
            ruta.write_bytes(b"contenido sintetico")
            with patch(
                "apps.dashboard.management.commands.importar_ubicaciones_esperadas."
                "pd.read_excel"
            ) as mock_read_excel, patch.object(
                ubicaciones_repository,
                "persistir_importacion",
            ) as mock_persistir, patch(
                "apps.dashboard.management.commands.importar_ubicaciones_esperadas."
                "registrar_log_importacion"
            ):
                with self.assertRaisesRegex(CommandError, "Formato no soportado"):
                    self.comando.handle(ruta_excel=str(ruta))

        mock_read_excel.assert_not_called()
        mock_persistir.assert_not_called()

    def test_excel_sin_hoja_version_db_se_rechaza_sin_oracle(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio, [self.fila_valida()], hoja="OtraHoja")
            with patch(
                "apps.dashboard.services.oracle_connection.obtener_conexion_oracle"
            ) as mock_conexion, patch(
                "apps.dashboard.management.commands.importar_ubicaciones_esperadas.registrar_log_importacion"
            ) as mock_log:
                with self.assertRaisesRegex(
                    CommandError,
                    "No se encontró la hoja Version_DB",
                ):
                    self.comando.handle(ruta_excel=str(ruta))

        mock_conexion.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("No se encontró la hoja Version_DB", self.stderr.getvalue())

    def test_excel_sin_columnas_requeridas_no_llega_al_repository(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio, [{"Columna ajena": "dato"}])
            with patch.object(
                ubicaciones_repository,
                "persistir_importacion",
            ) as mock_persistir, patch(
                "apps.dashboard.management.commands.importar_ubicaciones_esperadas."
                "registrar_log_importacion"
            ) as mock_log:
                with self.assertRaisesRegex(CommandError, "Faltan columnas requeridas"):
                    self.comando.handle(ruta_excel=str(ruta))

        mock_persistir.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")

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
                resultado = self.validar_dataframe(
                    pd.DataFrame([self.fila_valida(operativa)])
                )
                self.assertTrue(resultado.es_valido)
                datos = resultado.registros[0]
                self.assertEqual(datos["NOMBRE"], "Zona sintética")
                self.assertEqual(datos["LATITUD_ESPERADA"], -33.45)
                self.assertEqual(datos["LONGITUD_ESPERADA"], -70.66)
                self.assertEqual(datos["RADIO_METROS"], 150.0)
                self.assertEqual(datos["OPERATIVA"], 1)
                self.assertEqual(datos["ORIGEN_UBICACION"], "excel")

    def test_operativa_no_usa_referencia_laboratorio(self):
        resultado = self.validar_dataframe(pd.DataFrame([
            self.fila_valida(
                "NO",
                Latitud=None,
                Longitud=None,
                Radio=None,
            )
        ]))
        self.assertTrue(resultado.es_valido)
        datos = resultado.registros[0]

        self.assertEqual(datos["NOMBRE"], NOMBRE_LABORATORIO_ZP)
        self.assertEqual(datos["LATITUD_ESPERADA"], LATITUD_LABORATORIO_ZP)
        self.assertEqual(datos["LONGITUD_ESPERADA"], LONGITUD_LABORATORIO_ZP)
        self.assertEqual(datos["RADIO_METROS"], RADIO_LABORATORIO_ZP)
        self.assertEqual(datos["OPERATIVA"], 0)
        self.assertEqual(datos["ORIGEN_UBICACION"], "laboratorio")

    def test_operatividad_invalida_rechaza_dataset(self):
        resultado = self.validar_dataframe(pd.DataFrame([
            self.fila_valida("QUIZÁS")
        ]))
        self.assertFalse(resultado.es_valido)
        self.assertEqual(resultado.incidencias[0].campo, "OPERATIVA")

    def test_fila_sin_amid_rechaza_dataset(self):
        resultado = self.validar_dataframe(pd.DataFrame([
            self.fila_valida(IDDS=None)
        ]))
        self.assertFalse(resultado.es_valido)
        self.assertEqual(resultado.incidencias[0].campo, "IDDS")

    def test_operativa_si_sin_coordenadas_o_radio_validos_rechaza_dataset(self):
        for campo in ("Latitud", "Longitud", "Radio"):
            with self.subTest(campo=campo):
                resultado = self.validar_dataframe(pd.DataFrame([
                    self.fila_valida(**{campo: "inválido"})
                ]))
                self.assertFalse(resultado.es_valido)

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
                ruta,
                error_upsert=RuntimeError("fallo Oracle sintético"),
                esperar_error=True,
            )

        conexion.commit.assert_not_called()
        conexion.rollback.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("Error importando ubicaciones a Oracle", self.stderr.getvalue())
        self.assertIn("fallo Oracle sintético", self.stderr.getvalue())

    def test_error_semantico_no_llama_repository_ni_abre_oracle(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio, [self.fila_valida(IDDS=None)])
            with patch.object(
                ubicaciones_repository, "persistir_importacion"
            ) as mock_persistir, patch(
                "apps.dashboard.services.oracle_connection.obtener_conexion_oracle"
            ) as mock_conexion, patch(
                "apps.dashboard.management.commands.importar_ubicaciones_esperadas."
                "registrar_log_importacion"
            ) as mock_log:
                with self.assertRaisesRegex(CommandError, "Oracle no fue modificado"):
                    self.comando.handle(ruta_excel=str(ruta))

        mock_persistir.assert_not_called()
        mock_conexion.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("Fila 2", self.stderr.getvalue())
        self.assertIn("IDDS", self.stderr.getvalue())

    def test_muchos_errores_se_agregan_antes_del_repository(self):
        filas = [
            self.fila_valida(IDDS=None, Nombre="", Operativa="S"),
            self.fila_valida(IDDS=7500002, Latitud=999),
        ]
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio, filas)
            with patch.object(
                ubicaciones_repository, "persistir_importacion"
            ) as mock_persistir, patch(
                "apps.dashboard.management.commands.importar_ubicaciones_esperadas."
                "registrar_log_importacion"
            ) as mock_log:
                with self.assertRaises(CommandError):
                    self.comando.handle(ruta_excel=str(ruta))

        mock_persistir.assert_not_called()
        self.assertIn("4 errores en 2 filas", self.stderr.getvalue())
        self.assertIn("Fila 2", self.stderr.getvalue())
        self.assertIn("Fila 3", self.stderr.getvalue())
        self.assertIn("Incidencias: 4", mock_log.call_args.kwargs["mensaje"])

    def test_dataset_valido_llega_completo_y_materializado_al_repository(self):
        filas = [self.fila_valida(), self.fila_valida(IDDS=7500002)]
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio, filas)
            with patch.object(
                ubicaciones_repository, "persistir_importacion"
            ) as mock_persistir, patch(
                "apps.dashboard.management.commands.importar_ubicaciones_esperadas."
                "registrar_log_importacion"
            ):
                self.comando.handle(ruta_excel=str(ruta))

        argumentos = mock_persistir.call_args.kwargs
        self.assertIsInstance(argumentos["filas_normalizadas"], list)
        self.assertEqual(len(argumentos["filas_normalizadas"]), 2)
        self.assertEqual(argumentos["amids_presentes"], {"7500001", "7500002"})

    def test_fila_invalida_presente_no_puede_convertirse_en_falso_ausente(self):
        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio, [self.fila_valida(Operativa="S")])
            with patch.object(
                ubicaciones_repository, "persistir_importacion"
            ) as mock_persistir, patch.object(
                ubicaciones_repository, "mover_ausentes_a_laboratorio"
            ) as mock_ausentes, patch(
                "apps.dashboard.management.commands.importar_ubicaciones_esperadas."
                "registrar_log_importacion"
            ):
                with self.assertRaises(CommandError):
                    self.comando.handle(ruta_excel=str(ruta))

        mock_persistir.assert_not_called()
        mock_ausentes.assert_not_called()


class ImportarUbicacionesEsperadasTests(SimpleTestCase):
    def test_ausentes_usan_maestro_activo_y_respetan_amids_del_excel(self):
        cursor = MagicMock()
        cursor.description = [("AMID",), ("SERIE_VALIDADOR",)]
        cursor.fetchall.return_value = [
            ("750001", "SERIE-1"),
            ("750002", None),
        ]

        referencia_laboratorio = {
            "NOMBRE": "Laboratorio Zonas Pagas",
            "LATITUD_ESPERADA": -33.437191,
            "LONGITUD_ESPERADA": -70.656102,
            "RADIO_METROS": 150,
            "OPERATIVA": 0,
            "ORIGEN_UBICACION": "laboratorio_default",
        }
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
        ) as mock_crear:
            resultado = ubicaciones_repository.mover_ausentes_a_laboratorio(
                cursor=cursor,
                amids_excel={"750001"},
                fecha_carga=datetime(2026, 8, 27, 12, 0),
                archivo_origen="ZONA PAGA V755.xlsx",
                version_zp="V755",
                referencia_laboratorio=referencia_laboratorio,
            )

        consulta_maestro = cursor.execute.call_args.args[0]
        self.assertIn("AMID_MAESTRO_ALERTAS", consulta_maestro)
        self.assertIn("WHERE ACTIVO = 1", consulta_maestro)
        self.assertIn(
            "LEFT JOIN USR_LAB.UBICACION_ESPERADA_VALIDADOR",
            consulta_maestro,
        )

        mock_upsert.assert_called_once()
        datos_laboratorio = mock_upsert.call_args.args[1]
        self.assertEqual(datos_laboratorio["AMID"], "750002")
        self.assertEqual(datos_laboratorio["NOMBRE"], "Laboratorio Zonas Pagas")
        self.assertEqual(datos_laboratorio["OPERATIVA"], 0)
        self.assertIsNone(datos_laboratorio["HORARIO"])
        self.assertIsNone(datos_laboratorio["HORARIO_LABORAL_PM"])
        self.assertIsNone(datos_laboratorio["HORARIO_SABADO"])
        self.assertIsNone(datos_laboratorio["HORARIO_DOMINGO"])

        mock_crear.assert_called_once()
        datos_historial = mock_crear.call_args.args[1]
        self.assertEqual(
            datos_historial["ORIGEN_UBICACION"],
            "laboratorio_default",
        )
        self.assertEqual(resultado, (1, 0, 1))
