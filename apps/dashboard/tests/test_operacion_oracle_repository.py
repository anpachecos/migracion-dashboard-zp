from datetime import datetime
from unittest.mock import call, patch

from django.test import SimpleTestCase

from apps.dashboard.repositories import operacion_oracle_repository


class OperacionOracleRepositoryTests(SimpleTestCase):
    def obtener_cursor(self, mock_conexion):
        return (
            mock_conexion.return_value.__enter__.return_value
            .cursor.return_value.__enter__.return_value
        )

    @patch(
        "apps.dashboard.repositories.operacion_oracle_repository."
        "obtener_conexion_oracle"
    )
    def test_resumenes_conservan_tres_queries_una_conexion_y_filas(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        ahora = datetime(2026, 9, 14, 12, 0)
        filas = (
            (10, 8, ahora, ahora, ahora),
            (5, ahora),
            (4,),
        )
        cursor.fetchone.side_effect = filas

        resultado = operacion_oracle_repository.obtener_resumenes_estado()

        self.assertEqual(mock_conexion.call_count, 1)
        self.assertEqual(cursor.execute.call_count, 3)
        queries = [llamada.args[0] for llamada in cursor.execute.call_args_list]
        self.assertIn("FROM USR_LAB.BATERIA_BLOQUE_30MIN", queries[0])
        self.assertIn("SUM(", queries[0])
        self.assertIn("FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR", queries[1])
        self.assertIn("FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA", queries[2])
        self.assertIn("WHERE FECHA_FIN_VIGENCIA IS NULL", queries[2])
        self.assertEqual(resultado, filas)

    @patch(
        "apps.dashboard.repositories.operacion_oracle_repository."
        "obtener_conexion_oracle"
    )
    def test_resumenes_conservan_filas_none(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.fetchone.side_effect = [None, None, None]

        resultado = operacion_oracle_repository.obtener_resumenes_estado()

        self.assertEqual(resultado, (None, None, None))

    @patch(
        "apps.dashboard.repositories.operacion_oracle_repository."
        "obtener_conexion_oracle"
    )
    def test_sysdate_conserva_sql_exacto_y_fila(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        fila = (datetime(2026, 9, 14, 12, 0),)
        cursor.fetchone.return_value = fila

        resultado = operacion_oracle_repository.obtener_sysdate()

        self.assertEqual(
            cursor.execute.call_args_list,
            [call("SELECT SYSDATE FROM dual")],
        )
        self.assertEqual(resultado, fila)
