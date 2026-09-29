from unittest.mock import patch

from django.test import SimpleTestCase

from apps.dashboard.repositories import alertas_repository


class AlertasRepositoryTests(SimpleTestCase):
    def obtener_cursor(self, mock_conexion):
        return mock_conexion.return_value.__enter__.return_value.cursor.return_value

    def test_filtros_conservan_condiciones_dinamicas_y_variables_enlazadas(self):
        filtros, parametros = alertas_repository.armar_filtros_alertas(
            amid="7500001",
            ubicacion=" zona norte ",
            nivel="critica",
            nivel_gps="alta",
            nivel_bateria="advertencia",
            tipo_alerta="GPS",
            problema="gps_racha",
            estatus="antiguo",
            amids_excluidos=[7500002, "7500003"],
            ubicaciones_excluidas=["Laboratorio", "Bodega"],
            ubicacion_sin_asignar="Sin ubicación asignada",
        )

        self.assertEqual(
            filtros,
            [
                "TIENE_ALERTA = 1",
                "r.AMID = :amid",
                "UPPER(NVL(TRIM(u.NOMBRE), :ubicacion_sin_asignar)) LIKE :ubicacion",
                "NIVEL_ALERTA_GLOBAL = :nivel",
                "NIVEL_ALERTA_GPS = :nivel_gps",
                "NIVEL_ALERTA_BATERIA = :nivel_bateria",
                "NIVEL_ALERTA_GPS <> 'OK'",
                "(RACHA_MAX_GPS_CERO > 0)",
                "(ULTIMO_ESTATUS >= TRUNC(SYSDATE) AND ULTIMO_ESTATUS < SYSDATE - (1/24))",
                "r.AMID NOT IN (:amid_excluido_0, :amid_excluido_1)",
                "NVL(TRIM(u.NOMBRE), :ubicacion_sin_asignar) NOT IN (:ubicacion_excluida_0, :ubicacion_excluida_1)",
            ],
        )
        self.assertEqual(
            parametros,
            {
                "amid": 7500001,
                "ubicacion_sin_asignar": "Sin ubicación asignada",
                "ubicacion": "%ZONA NORTE%",
                "nivel": "CRITICA",
                "nivel_gps": "ALTA",
                "nivel_bateria": "ADVERTENCIA",
                "amid_excluido_0": 7500002,
                "amid_excluido_1": 7500003,
                "ubicacion_excluida_0": "Laboratorio",
                "ubicacion_excluida_1": "Bodega",
            },
        )

    def test_orden_conserva_prioridades_direccion_estatus_y_desempate(self):
        resultado = alertas_repository.construir_orden_alertas(
            (
                ("prioridad", "desc"),
                ("gps", "asc"),
                ("bateria", "desc"),
                ("estatus", "desc"),
            )
        )

        self.assertIn("CASE NIVEL_ALERTA_GLOBAL", resultado)
        self.assertIn("CASE NIVEL_ALERTA_GPS", resultado)
        self.assertIn("CASE NIVEL_ALERTA_BATERIA", resultado)
        self.assertIn("ULTIMO_ESTATUS ASC NULLS FIRST", resultado)
        self.assertTrue(resultado.endswith("AMID ASC"))

    @patch("apps.dashboard.repositories.alertas_repository.obtener_conexion_oracle")
    def test_contar_conserva_query_filtros_parametros_y_escalar(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.fetchone.return_value = (4,)

        resultado = alertas_repository.contar_alertas_validadores(
            "Sin ubicación asignada",
            amid="7500001",
            nivel="alta",
        )

        query, parametros = cursor.execute.call_args.args
        self.assertIn("SELECT COUNT(*)", query)
        self.assertIn("FROM USR_LAB.VW_ALERTA_VALIDADOR_ACTIVA r", query)
        self.assertIn("LEFT JOIN USR_LAB.UBICACION_ESPERADA_VALIDADOR u", query)
        self.assertIn("TIENE_ALERTA = 1 AND r.AMID = :amid", query)
        self.assertIn("NIVEL_ALERTA_GLOBAL = :nivel", query)
        self.assertEqual(parametros, {"amid": 7500001, "nivel": "ALTA"})
        self.assertEqual(resultado, 4)

    @patch("apps.dashboard.repositories.alertas_repository.obtener_conexion_oracle")
    def test_contar_sin_fila_retorna_none(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.fetchone.return_value = None

        resultado = alertas_repository.contar_alertas_validadores(
            "Sin ubicación asignada"
        )

        self.assertIsNone(resultado)

    @patch("apps.dashboard.repositories.alertas_repository.obtener_conexion_oracle")
    def test_listado_conserva_paginacion_orden_parametros_y_diccionarios(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.description = [("AMID",), ("NIVEL_ALERTA_GLOBAL",), ("RN",)]
        cursor.fetchall.return_value = [(7500001, "CRITICA", 6)]

        resultado = alertas_repository.obtener_alertas_validadores(
            "Sin ubicación asignada",
            limite="10",
            offset="5",
            ordenar=True,
            orden=(("prioridad", "asc"),),
            solo_con_alerta=False,
            ubicacion="Centro",
        )

        query, parametros = cursor.execute.call_args.args
        self.assertIn("ROW_NUMBER() OVER (ORDER BY", query)
        self.assertIn("CASE NIVEL_ALERTA_GLOBAL", query)
        self.assertIn("WHERE rn BETWEEN :offset + 1 AND :offset + :limite", query)
        self.assertIn("UPPER(NVL(TRIM(u.NOMBRE), :ubicacion_sin_asignar))", query)
        self.assertEqual(
            parametros,
            {
                "ubicacion_sin_asignar": "Sin ubicación asignada",
                "ubicacion": "%CENTRO%",
                "offset": 5,
                "limite": 10,
            },
        )
        self.assertEqual(
            resultado,
            [{"amid": 7500001, "nivel_alerta_global": "CRITICA", "rn": 6}],
        )

    @patch("apps.dashboard.repositories.alertas_repository.obtener_conexion_oracle")
    def test_listado_sin_ordenar_conserva_orden_por_amid(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.description = []
        cursor.fetchall.return_value = []

        resultado = alertas_repository.obtener_alertas_validadores(
            "Sin ubicación asignada",
            limite=10,
            offset=0,
            ordenar=False,
            orden=None,
        )

        query = cursor.execute.call_args.args[0]
        self.assertIn("ROW_NUMBER() OVER (ORDER BY AMID ASC)", query)
        self.assertEqual(resultado, [])

    @patch("apps.dashboard.repositories.alertas_repository.obtener_conexion_oracle")
    def test_ubicaciones_conservan_distinct_orden_parametro_y_filtro_de_filas(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.fetchall.return_value = [("Bodega",), (None,), (), ("Laboratorio",)]

        resultado = alertas_repository.obtener_ubicaciones_alertas_disponibles(
            "Sin ubicación asignada"
        )

        query, parametros = cursor.execute.call_args.args
        self.assertIn("SELECT DISTINCT", query)
        self.assertIn("ORDER BY ubicacion_actual", query)
        self.assertEqual(
            parametros,
            {"ubicacion_sin_asignar": "Sin ubicación asignada"},
        )
        self.assertEqual(resultado, ["Bodega", "Laboratorio"])

    @patch("apps.dashboard.repositories.alertas_repository.obtener_conexion_oracle")
    def test_busqueda_amid_conserva_prefijo_limite_orden_y_retorno(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.fetchall.return_value = [(7500001,), (None,), (), (7500002,)]

        resultado = alertas_repository.buscar_amids_alertas("750", 15)

        query, parametros = cursor.execute.call_args.args
        self.assertIn("TO_CHAR(r.AMID) LIKE :patron", query)
        self.assertIn("ORDER BY r.AMID", query)
        self.assertIn("WHERE ROWNUM <= :limite", query)
        self.assertEqual(parametros, {"patron": "750%", "limite": 15})
        self.assertEqual(resultado, [7500001, 7500002])

    @patch("apps.dashboard.repositories.alertas_repository.obtener_conexion_oracle")
    def test_resumen_conserva_agregados_exclusiones_parametros_y_fila(
        self,
        mock_conexion,
    ):
        cursor = self.obtener_cursor(mock_conexion)
        fila = (8, 5, 1, 2, 2, 3, 4, 2, 7, None)
        cursor.fetchone.return_value = fila

        resultado = alertas_repository.obtener_resumen_alertas(
            "Sin ubicación asignada",
            amids_excluidos=[7500001],
            ubicaciones_excluidas=["Laboratorio"],
        )

        query, parametros = cursor.execute.call_args.args
        self.assertIn("COUNT(*) AS total_validadores", query)
        self.assertIn("SUM(NVL(CAIDAS_HIST, 0)) AS total_caidas_bateria", query)
        self.assertIn("r.AMID NOT IN (:amid_excluido_0)", query)
        self.assertIn("NOT IN (:ubicacion_excluida_0)", query)
        self.assertEqual(
            parametros,
            {
                "amid_excluido_0": 7500001,
                "ubicacion_excluida_0": "Laboratorio",
                "ubicacion_sin_asignar": "Sin ubicación asignada",
            },
        )
        self.assertEqual(resultado, fila)

    @patch("apps.dashboard.repositories.alertas_repository.obtener_conexion_oracle")
    def test_resumen_sin_fila_retorna_none(self, mock_conexion):
        cursor = self.obtener_cursor(mock_conexion)
        cursor.fetchone.return_value = None

        resultado = alertas_repository.obtener_resumen_alertas(
            "Sin ubicación asignada"
        )

        self.assertIsNone(resultado)
