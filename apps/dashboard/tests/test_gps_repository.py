from datetime import datetime
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.dashboard.repositories import gps_repository


class GpsRepositoryTests(SimpleTestCase):
    def obtener_cursor(self, mock_conexion):
        return (
            mock_conexion.return_value.__enter__.return_value
            .cursor.return_value.__enter__.return_value
        )

    @patch("apps.dashboard.repositories.gps_repository.obtener_conexion_oracle")
    def test_registros_conservan_consulta_anterior_rango_parametros_y_retorno(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        fecha_anterior = datetime(2026, 9, 10, 7, 30)
        cursor.fetchone.return_value = (fecha_anterior,)
        cursor.description = [("ID",), ("AMID",), ("FECHA_HORA",)]
        cursor.fetchall.return_value = [
            (1, 7500001, datetime(2026, 9, 10, 8, 0)),
        ]

        resultado = gps_repository.obtener_registros_gps(
            amid="7500001",
            fecha_inicio="2026-09-10 08:00:00",
            fecha_fin="2026-09-10 09:00:00",
        )

        llamada_anterior, llamada_rango = cursor.execute.call_args_list
        query_anterior, parametros_anteriores = llamada_anterior.args
        query_rango, parametros_rango = llamada_rango.args
        self.assertIn("FECHA_REGISTRO < TO_DATE(:fecha_inicio", query_anterior)
        self.assertIn("ORDER BY FECHA_REGISTRO DESC, ID DESC", query_anterior)
        self.assertIn("WHERE ROWNUM = 1", query_anterior)
        self.assertEqual(
            parametros_anteriores,
            {"amid": 7500001, "fecha_inicio": "2026-09-10 08:00:00"},
        )
        self.assertIn("FECHA_REGISTRO >= TO_DATE(:fecha_inicio", query_rango)
        self.assertIn("FECHA_REGISTRO < TO_DATE(:fecha_fin", query_rango)
        self.assertIn("ORDER BY FECHA_REGISTRO, ID", query_rango)
        self.assertEqual(
            parametros_rango,
            {
                "amid": 7500001,
                "fecha_inicio": "2026-09-10 08:00:00",
                "fecha_fin": "2026-09-10 09:00:00",
            },
        )
        self.assertEqual(resultado["fecha_hora_anterior"], fecha_anterior)
        self.assertEqual(
            resultado["registros"],
            [{"id": 1, "amid": 7500001, "fecha_hora": datetime(2026, 9, 10, 8, 0)}],
        )

    @patch("apps.dashboard.repositories.gps_repository.obtener_conexion_oracle")
    def test_registros_sin_filas_conservan_resultado_vacio(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.fetchone.return_value = None
        cursor.description = []
        cursor.fetchall.return_value = []

        resultado = gps_repository.obtener_registros_gps(
            amid="7500001",
            fecha_inicio="2026-09-10 08:00:00",
            fecha_fin="2026-09-10 09:00:00",
        )

        self.assertEqual(
            resultado,
            {"fecha_hora_anterior": None, "registros": []},
        )

    @patch("apps.dashboard.repositories.gps_repository.obtener_conexion_oracle")
    def test_ultimo_gps_valido_conserva_filtros_y_diccionario(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.description = [("ID",), ("AMID",), ("LATITUD",), ("LONGITUD",)]
        cursor.fetchone.return_value = (3, 7500001, -33.45, -70.66)

        resultado = gps_repository.obtener_ultimo_registro_gps_valido("7500001")

        query, parametros = cursor.execute.call_args.args
        self.assertIn("AND FECHA_HORA IS NOT NULL", query)
        self.assertIn("AND NOT (LATITUD = 0 AND LONGITUD = 0)", query)
        self.assertIn("ORDER BY FECHA_HORA DESC", query)
        self.assertIn("WHERE ROWNUM = 1", query)
        self.assertEqual(parametros, {"amid": 7500001})
        self.assertEqual(
            resultado,
            {"id": 3, "amid": 7500001, "latitud": -33.45, "longitud": -70.66},
        )

    @patch("apps.dashboard.repositories.gps_repository.obtener_conexion_oracle")
    def test_ultimo_gps_valido_sin_fila_retorna_none(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.fetchone.return_value = None

        resultado = gps_repository.obtener_ultimo_registro_gps_valido("7500001")

        self.assertIsNone(resultado)

    @patch("apps.dashboard.repositories.gps_repository.obtener_conexion_oracle")
    def test_datos_ubicacion_conservan_dos_queries_parametro_y_retorno(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        historial = ("7500001", "Zona histórica")
        vigente = ("7500001", "Zona vigente")

        def ejecutar(query, _parametros):
            if "HISTORIAL_UBICACION_ESPERADA" in query:
                cursor.description = [("AMID",), ("NOMBRE",)]
            else:
                cursor.description = [("AMID",), ("NOMBRE",)]

        cursor.execute.side_effect = ejecutar
        cursor.fetchall.return_value = [historial]
        cursor.fetchone.return_value = vigente

        resultado = gps_repository.obtener_datos_ubicacion_amid(" 7500001 ")

        self.assertEqual(cursor.execute.call_count, 2)
        query_historial = cursor.execute.call_args_list[0].args[0]
        query_vigente = cursor.execute.call_args_list[1].args[0]
        self.assertIn("FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA", query_historial)
        self.assertIn("ORDER BY FECHA_INICIO_VIGENCIA", query_historial)
        self.assertIn("FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR", query_vigente)
        self.assertEqual(
            [llamada.args[1] for llamada in cursor.execute.call_args_list],
            [{"amid": "7500001"}, {"amid": "7500001"}],
        )
        self.assertEqual(
            resultado,
            {
                "historial": [{"AMID": "7500001", "NOMBRE": "Zona histórica"}],
                "vigente": {"AMID": "7500001", "NOMBRE": "Zona vigente"},
            },
        )

    @patch("apps.dashboard.repositories.gps_repository.obtener_conexion_oracle")
    def test_datos_ubicacion_sin_filas_conserva_estructuras_vacias(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.description = []
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = None

        resultado = gps_repository.obtener_datos_ubicacion_amid("7500001")

        self.assertEqual(resultado, {"historial": [], "vigente": None})
