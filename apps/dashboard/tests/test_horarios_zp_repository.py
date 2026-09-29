from unittest.mock import patch

from django.test import SimpleTestCase

from apps.dashboard.repositories import horarios_zp_repository


class HorariosZonaPagaRepositoryTests(SimpleTestCase):
    def obtener_cursor(self, mock_conexion):
        return (
            mock_conexion.return_value.__enter__.return_value
            .cursor.return_value.__enter__.return_value
        )

    @patch(
        "apps.dashboard.repositories.horarios_zp_repository.obtener_conexion_oracle"
    )
    def test_horario_conserva_sql_parametro_y_diccionario(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.description = [("AMID",), ("NOMBRE",), ("HORARIO",)]
        cursor.fetchone.return_value = ("7500001", "Zona sintética", "08:00-18:00")

        resultado = horarios_zp_repository.obtener_datos_horario_zp(" 7500001 ")

        query, parametros = cursor.execute.call_args.args
        self.assertIn("SELECT AMID, NOMBRE, HORARIO, HORARIO_LABORAL_PM", query)
        self.assertIn("FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR", query)
        self.assertIn("WHERE AMID = :amid", query)
        self.assertEqual(parametros, {"amid": "7500001"})
        self.assertEqual(
            resultado,
            {
                "AMID": "7500001",
                "NOMBRE": "Zona sintética",
                "HORARIO": "08:00-18:00",
            },
        )

    @patch(
        "apps.dashboard.repositories.horarios_zp_repository.obtener_conexion_oracle"
    )
    def test_horario_sin_fila_retorna_none(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.fetchone.return_value = None

        resultado = horarios_zp_repository.obtener_datos_horario_zp("7500001")

        self.assertIsNone(resultado)
