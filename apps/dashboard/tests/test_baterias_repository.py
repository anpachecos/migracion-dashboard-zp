from datetime import datetime
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.dashboard.repositories import baterias_repository


class BateriasRepositoryTests(SimpleTestCase):
    def obtener_cursor(self, mock_conexion):
        return (
            mock_conexion.return_value.__enter__.return_value
            .cursor.return_value.__enter__.return_value
        )

    @patch(
        "apps.dashboard.repositories.baterias_repository.obtener_conexion_oracle"
    )
    def test_obtener_ultimo_registro_conserva_query_parametro_y_diccionario(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.description = [("ID",), ("AMID",)]
        cursor.fetchone.return_value = (2, 7500001)

        resultado = baterias_repository.obtener_ultimo_registro("7500001")

        query, parametros = cursor.execute.call_args.args
        self.assertIn("FROM USR_LAB.VW_ESTATUS_ZP_DJANGO", query)
        self.assertIn("ORDER BY FECHA_HORA DESC", query)
        self.assertIn("WHERE ROWNUM = 1", query)
        self.assertEqual(parametros, {"amid": 7500001})
        self.assertEqual(resultado, {"id": 2, "amid": 7500001})

    @patch(
        "apps.dashboard.repositories.baterias_repository.obtener_conexion_oracle"
    )
    def test_obtener_bloques_conserva_rango_orden_y_lista_de_diccionarios(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.description = [("AMID",), ("PORCENTAJE_BATERIA",)]
        cursor.fetchall.return_value = [(7500001, 64), (7500001, 61)]
        fecha_inicio = datetime(2026, 9, 1)
        fecha_fin = datetime(2026, 9, 2)

        resultado = baterias_repository.obtener_bloques_bateria(
            "7500001",
            fecha_inicio,
            fecha_fin,
        )

        query, parametros = cursor.execute.call_args.args
        self.assertIn("FROM USR_LAB.BATERIA_BLOQUE_30MIN", query)
        self.assertIn("FECHA_HORA_BLOQUE >= :fecha_inicio", query)
        self.assertIn("FECHA_HORA_BLOQUE < :fecha_fin", query)
        self.assertIn("ORDER BY FECHA_HORA_BLOQUE", query)
        self.assertEqual(
            parametros,
            {
                "amid": 7500001,
                "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin,
            },
        )
        self.assertEqual(
            resultado,
            [
                {"amid": 7500001, "porcentaje_bateria": 64},
                {"amid": 7500001, "porcentaje_bateria": 61},
            ],
        )

    @patch(
        "apps.dashboard.repositories.baterias_repository.obtener_conexion_oracle"
    )
    def test_obtener_detalle_caidas_conserva_orden_y_lista_de_diccionarios(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.description = [("AMID",), ("CAIDA_DIF",)]
        cursor.fetchall.return_value = [(7500001, 7)]

        resultado = baterias_repository.obtener_detalle_caidas_bateria("7500001")

        query, parametros = cursor.execute.call_args.args
        self.assertIn("FROM USR_LAB.ALERTA_BATERIA_CAIDA_EVENTO", query)
        self.assertIn("ORDER BY FECHA_CAIDA DESC", query)
        self.assertEqual(parametros, {"amid": 7500001})
        self.assertEqual(resultado, [{"amid": 7500001, "caida_dif": 7}])

    @patch(
        "apps.dashboard.repositories.baterias_repository.obtener_conexion_oracle"
    )
    def test_obtener_resumen_conserva_parametro_y_diccionario(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.description = [("AMID",), ("CAIDAS_HOY",)]
        cursor.fetchone.return_value = (7500001, 3)

        resultado = baterias_repository.obtener_resumen_alerta_bateria("7500001")

        query, parametros = cursor.execute.call_args.args
        self.assertIn("FROM USR_LAB.ALERTA_VALIDADOR_RESUMEN", query)
        self.assertIn("WHERE AMID = :amid", query)
        self.assertEqual(parametros, {"amid": 7500001})
        self.assertEqual(resultado, {"amid": 7500001, "caidas_hoy": 3})
