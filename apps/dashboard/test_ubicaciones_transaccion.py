from datetime import datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pandas as pd
from django.test import SimpleTestCase

from apps.dashboard.management.commands.importar_ubicaciones_esperadas import (
    Command as ImportarUbicacionesCommand,
)
from apps.dashboard.management.commands.limpiar_historial_ubicacion_oracle import (
    Command as LimpiarHistorialCommand,
)
from apps.dashboard.services.ubicaciones_service import (
    sincronizar_amids_ubicaciones_oracle,
)


class ImportacionUbicacionesTransaccionCaracterizacionTests(SimpleTestCase):
    FECHA_CARGA = datetime(2026, 9, 15, 12, 0)

    def crear_excel(self, directorio):
        ruta = Path(directorio) / "ZONA PAGA V900.xlsx"
        pd.DataFrame(
            [
                {
                    "IDDS": 7500900,
                    "Nombre": "Zona sintética",
                    "Serie Val": "SERIE-900",
                    "Latitud": -33.45,
                    "Longitud": -70.66,
                    "Operativa": "SI",
                    "Radio": 150,
                }
            ]
        ).to_excel(ruta, sheet_name="Version_DB", index=False)
        return ruta

    def preparar_oracle(self):
        conexion = MagicMock(name="conexion_oracle_falsa")
        cursor = MagicMock(name="cursor_oracle_falso")
        conexion.cursor.return_value.__enter__.return_value = cursor
        contexto = MagicMock(name="contexto_conexion_falsa")
        contexto.__enter__.return_value = conexion
        return contexto, conexion, cursor

    def ejecutar(self, ruta, contexto):
        stdout = StringIO()
        stderr = StringIO()
        comando = ImportarUbicacionesCommand(stdout=stdout, stderr=stderr)
        with patch(
            "apps.dashboard.repositories.ubicaciones_repository."
            "obtener_conexion_oracle",
            return_value=contexto,
        ), patch(
            "apps.dashboard.management.commands.importar_ubicaciones_esperadas."
            "registrar_log_importacion"
        ) as mock_log, patch.object(
            comando,
            "ahora_oracle",
            return_value=self.FECHA_CARGA,
        ):
            comando.handle(ruta_excel=str(ruta))
        return stdout, stderr, mock_log

    def test_orden_transaccional_fila_nueva_ausentes_y_commit(self):
        eventos = []
        contexto, conexion, cursor = self.preparar_oracle()
        cursor.fetchone.side_effect = [(0,), None]
        cursor.fetchall.return_value = []

        def ejecutar(sql, _parametros=None):
            if "SELECT COUNT(*)" in sql:
                eventos.append("LECTURA_VIGENTE")
            elif "MERGE INTO" in sql:
                eventos.append("MERGE_VIGENTE")
            elif "SELECT\n                ID," in sql:
                eventos.append("LECTURA_HISTORIAL")
            elif "INSERT INTO" in sql:
                eventos.append("INSERT_HISTORIAL")
            elif "AMID_MAESTRO_ALERTAS" in sql:
                eventos.append("LECTURA_AUSENTES")

        cursor.execute.side_effect = ejecutar
        conexion.commit.side_effect = lambda: eventos.append("COMMIT")

        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio)
            _stdout, stderr, mock_log = self.ejecutar(ruta, contexto)

        self.assertEqual(
            eventos,
            [
                "LECTURA_VIGENTE",
                "MERGE_VIGENTE",
                "LECTURA_HISTORIAL",
                "INSERT_HISTORIAL",
                "LECTURA_AUSENTES",
                "COMMIT",
            ],
        )
        conexion.rollback.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "OK")
        self.assertEqual(stderr.getvalue(), "")

    def test_fallos_parciales_no_confirman_ni_hacen_rollback_explicito(self):
        casos = (
            ("SELECT COUNT(*)", "lectura vigente"),
            ("MERGE INTO", "merge"),
            ("INSERT INTO", "historial"),
            ("AMID_MAESTRO_ALERTAS", "ausentes"),
        )
        for fragmento, nombre in casos:
            with self.subTest(etapa=nombre), TemporaryDirectory() as directorio:
                contexto, conexion, cursor = self.preparar_oracle()
                cursor.fetchone.side_effect = [(0,), None]
                cursor.fetchall.return_value = []

                def ejecutar(sql, _parametros=None, objetivo=fragmento):
                    if objetivo in sql:
                        raise RuntimeError(f"fallo sintético {nombre}")

                cursor.execute.side_effect = ejecutar
                ruta = self.crear_excel(directorio)
                _stdout, stderr, mock_log = self.ejecutar(ruta, contexto)

                conexion.commit.assert_not_called()
                conexion.rollback.assert_not_called()
                self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
                self.assertIn(f"fallo sintético {nombre}", stderr.getvalue())

    def test_fallo_cerrando_historial_no_confirma_cambios_previos(self):
        contexto, conexion, cursor = self.preparar_oracle()
        historial = (
            9,
            "7500900",
            "Zona anterior",
            "SERIE-900",
            -33.45,
            -70.66,
            150,
            1,
            "excel",
            "V899",
        )
        cursor.fetchone.side_effect = [(1,), historial]

        def ejecutar(sql, _parametros=None):
            if "SELECT\n                ID," in sql:
                cursor.description = [
                    ("ID",),
                    ("AMID",),
                    ("NOMBRE",),
                    ("SERIE_VALIDADOR",),
                    ("LATITUD_ESPERADA",),
                    ("LONGITUD_ESPERADA",),
                    ("RADIO_METROS",),
                    ("OPERATIVA",),
                    ("ORIGEN_UBICACION",),
                    ("VERSION_ZP",),
                ]
            if "SET FECHA_FIN_VIGENCIA" in sql:
                raise RuntimeError("fallo sintético cierre historial")

        cursor.execute.side_effect = ejecutar

        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio)
            _stdout, stderr, mock_log = self.ejecutar(ruta, contexto)

        conexion.commit.assert_not_called()
        conexion.rollback.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("fallo sintético cierre historial", stderr.getvalue())

    def test_fallo_del_commit_se_captura_sin_rollback_explicito(self):
        contexto, conexion, cursor = self.preparar_oracle()
        cursor.fetchone.side_effect = [(0,), None]
        cursor.fetchall.return_value = []
        conexion.commit.side_effect = RuntimeError("fallo sintético commit")

        with TemporaryDirectory() as directorio:
            ruta = self.crear_excel(directorio)
            _stdout, stderr, mock_log = self.ejecutar(ruta, contexto)

        conexion.commit.assert_called_once_with()
        conexion.rollback.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("fallo sintético commit", stderr.getvalue())


class OperacionesUbicacionesCaracterizacionTests(SimpleTestCase):
    @patch(
        "apps.dashboard.repositories.ubicaciones_repository."
        "obtener_conexion_oracle"
    )
    def test_fallo_sincronizacion_propaga_sin_commit_ni_rollback(self, mock_conexion):
        conexion = mock_conexion.return_value.__enter__.return_value
        cursor = conexion.cursor.return_value.__enter__.return_value
        cursor.callproc.side_effect = RuntimeError("fallo sintético sincronización")

        with self.assertRaisesRegex(
            RuntimeError,
            "fallo sintético sincronización",
        ):
            sincronizar_amids_ubicaciones_oracle()

        conexion.commit.assert_not_called()
        conexion.rollback.assert_not_called()

    @patch(
        "apps.dashboard.repositories.ubicaciones_repository."
        "obtener_conexion_oracle"
    )
    @patch(
        "apps.dashboard.management.commands.limpiar_historial_ubicacion_oracle."
        "registrar_log_importacion"
    )
    def test_fallo_limpieza_se_captura_sin_commit_ni_rollback(
        self,
        mock_log,
        mock_conexion,
    ):
        stdout = StringIO()
        stderr = StringIO()
        comando = LimpiarHistorialCommand(stdout=stdout, stderr=stderr)
        conexion = mock_conexion.return_value.__enter__.return_value
        cursor = conexion.cursor.return_value.__enter__.return_value
        cursor.callproc.side_effect = RuntimeError("fallo sintético limpieza")

        comando.handle(dias_retencion=16)

        conexion.commit.assert_not_called()
        conexion.rollback.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("fallo sintético limpieza", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")
