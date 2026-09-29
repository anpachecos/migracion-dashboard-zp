from datetime import datetime
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.dashboard.repositories import estado_dashboard_repository
from apps.dashboard.views import obtener_registros_completos_oracle


class EstadoDashboardRepositoryTests(SimpleTestCase):
    def obtener_cursor(self, mock_conexion):
        return (
            mock_conexion.return_value.__enter__.return_value
            .cursor.return_value.__enter__.return_value
        )

    @patch(
        "apps.dashboard.repositories.estado_dashboard_repository."
        "obtener_conexion_oracle"
    )
    def test_ultima_carga_conserva_sql_sin_parametros_y_fila(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        fila = (datetime(2026, 9, 14, 12, 0),)
        cursor.fetchone.return_value = fila

        resultado = estado_dashboard_repository.obtener_ultima_carga_datos()

        query = cursor.execute.call_args.args[0]
        self.assertIn("SELECT MAX(FECHA_HORA_BLOQUE)", query)
        self.assertIn("FROM USR_LAB.BATERIA_BLOQUE_30MIN", query)
        self.assertIn("WHERE TIENE_DATO = 1", query)
        self.assertEqual(len(cursor.execute.call_args.args), 1)
        self.assertEqual(resultado, fila)

    @patch(
        "apps.dashboard.repositories.estado_dashboard_repository."
        "obtener_conexion_oracle"
    )
    def test_ultima_version_conserva_sql_sin_parametros_y_none(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.fetchone.return_value = None

        resultado = estado_dashboard_repository.obtener_ultima_version_zp()

        query = cursor.execute.call_args.args[0]
        self.assertIn("SELECT MAX(FECHA_CARGA)", query)
        self.assertIn("FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR", query)
        self.assertEqual(len(cursor.execute.call_args.args), 1)
        self.assertIsNone(resultado)

    @patch(
        "apps.dashboard.repositories.estado_dashboard_repository."
        "obtener_conexion_oracle"
    )
    def test_registros_conservan_sql_parametros_orden_y_diccionarios(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.description = [("ID",), ("AMID",), ("FECHA_HORA",)]
        fecha = datetime(2026, 9, 14, 8, 0)
        cursor.fetchall.return_value = [(1, 7500001, fecha)]

        resultado = estado_dashboard_repository.obtener_registros_completos(
            amid="7500001",
            fecha_inicio="2026-09-01 00:00:00",
            fecha_fin="2026-09-15 00:00:00",
        )

        query, parametros = cursor.execute.call_args.args
        self.assertIn("FROM USR_LAB.VW_ESTATUS_ZP_DJANGO", query)
        self.assertIn("FECHA_HORA >= TO_DATE(:fecha_inicio", query)
        self.assertIn("FECHA_HORA < TO_DATE(:fecha_fin", query)
        self.assertIn("ORDER BY FECHA_HORA", query)
        self.assertEqual(
            parametros,
            {
                "amid": 7500001,
                "fecha_inicio": "2026-09-01 00:00:00",
                "fecha_fin": "2026-09-15 00:00:00",
            },
        )
        self.assertEqual(
            resultado,
            [{"id": 1, "amid": 7500001, "fecha_hora": fecha}],
        )

    @patch(
        "apps.dashboard.repositories.estado_dashboard_repository."
        "obtener_conexion_oracle"
    )
    def test_registros_sin_filas_retorna_lista_vacia(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.description = []
        cursor.fetchall.return_value = []

        resultado = estado_dashboard_repository.obtener_registros_completos(
            amid=7500001,
            fecha_inicio="2026-09-01 00:00:00",
            fecha_fin="2026-09-15 00:00:00",
        )

        self.assertEqual(resultado, [])


class ViewsOracleRepositoryDelegationTests(SimpleTestCase):
    @patch(
        "apps.dashboard.views.estado_dashboard_repository."
        "obtener_registros_completos"
    )
    def test_view_conserva_formato_fechas_y_retorno(self, mock_registros):
        esperado = [{"amid": 7500001}]
        mock_registros.return_value = esperado

        resultado = obtener_registros_completos_oracle(
            amid="7500001",
            fecha_inicio=datetime(2026, 9, 1, 0, 0),
            fecha_fin=datetime(2026, 9, 15, 0, 0),
        )

        mock_registros.assert_called_once_with(
            amid="7500001",
            fecha_inicio="2026-09-01 00:00:00",
            fecha_fin="2026-09-15 00:00:00",
        )
        self.assertIs(resultado, esperado)
