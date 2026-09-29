from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.dashboard.repositories import reglas_alertas_repository
from apps.dashboard.services import reglas_alertas_service


class ReglasAlertasRepositoryTests(SimpleTestCase):
    TIPOS_VALIDOS = frozenset({"DETECCION", "CLASIFICACION"})

    def preparar_oracle(self, filas=None, rowcount=1):
        conexion = self.mock_conexion.return_value.__enter__.return_value
        cursor = conexion.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = filas or []
        cursor.rowcount = rowcount
        return conexion, cursor

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository."
        "obtener_conexion_oracle"
    )
    def test_obtener_reglas_conserva_sql_binds_orden_y_diccionarios(
        self,
        mock_conexion,
    ):
        self.mock_conexion = mock_conexion
        _conexion, cursor = self.preparar_oracle()
        cursor.description = [
            ("CLAVE",),
            ("VALOR_NUMERO",),
            ("TIPO_REGLA",),
        ]
        cursor.fetchall.return_value = [
            ("BAT_CAIDA_MIN_DETECTAR", Decimal("20"), "DETECCION")
        ]

        resultado = reglas_alertas_repository.obtener_reglas(
            ["BAT_CAIDA_MIN_DETECTAR", "GPS_CERO_HOY_ADV"]
        )

        query, parametros = cursor.execute.call_args.args
        self.assertIn("FROM USR_LAB.ALERTA_REGLA_PARAM", query)
        self.assertIn("WHERE CLAVE IN (:clave_1, :clave_2)", query)
        self.assertIn("ORDER BY CLAVE", query)
        self.assertEqual(
            parametros,
            {
                "clave_1": "BAT_CAIDA_MIN_DETECTAR",
                "clave_2": "GPS_CERO_HOY_ADV",
            },
        )
        self.assertEqual(
            resultado,
            [
                {
                    "clave": "BAT_CAIDA_MIN_DETECTAR",
                    "valor_numero": Decimal("20"),
                    "tipo_regla": "DETECCION",
                }
            ],
        )

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository."
        "obtener_conexion_oracle"
    )
    def test_obtener_reglas_sin_filas_retorna_lista_vacia(self, mock_conexion):
        self.mock_conexion = mock_conexion
        _conexion, cursor = self.preparar_oracle()
        cursor.description = []

        resultado = reglas_alertas_repository.obtener_reglas([])

        self.assertEqual(resultado, [])

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository."
        "obtener_conexion_oracle"
    )
    def test_actualizacion_conserva_orden_binds_transaccion_y_retorno(
        self,
        mock_conexion,
    ):
        self.mock_conexion = mock_conexion
        conexion, cursor = self.preparar_oracle(
            [("GPS_CERO_HOY_ADV", Decimal("2"), "clasificacion")]
        )
        eventos = []

        def ejecutar(query, parametros=None):
            if "FOR UPDATE" in query:
                eventos.append(("SELECT_FOR_UPDATE", parametros))
            elif query.lstrip().startswith("UPDATE"):
                eventos.append(("UPDATE", parametros))
            else:
                eventos.append(("PRC_VALIDAR", parametros))

        cursor.execute.side_effect = ejecutar
        conexion.commit.side_effect = lambda: eventos.append(("COMMIT", None))
        conexion.rollback.side_effect = lambda: eventos.append(("ROLLBACK", None))

        cambios = reglas_alertas_repository.actualizar_reglas(
            [("GPS_CERO_HOY_ADV", Decimal("3"))],
            tipos_permitidos=self.TIPOS_VALIDOS,
        )

        self.assertEqual(
            [evento[0] for evento in eventos],
            ["SELECT_FOR_UPDATE", "UPDATE", "PRC_VALIDAR", "COMMIT"],
        )
        query_select, parametros_select = cursor.execute.call_args_list[0].args
        query_update, parametros_update = cursor.execute.call_args_list[1].args
        query_procedure = cursor.execute.call_args_list[2].args[0]
        self.assertIn("SELECT CLAVE, VALOR_NUMERO, TIPO_REGLA", query_select)
        self.assertIn("FOR UPDATE", query_select)
        self.assertEqual(parametros_select, {"clave_1": "GPS_CERO_HOY_ADV"})
        self.assertIn("UPDATE USR_LAB.ALERTA_REGLA_PARAM", query_update)
        self.assertEqual(
            parametros_update,
            {
                "valor_numero": Decimal("3"),
                "clave": "GPS_CERO_HOY_ADV",
            },
        )
        self.assertEqual(
            query_procedure,
            "BEGIN USR_LAB.PRC_VALIDAR_REGLAS_ALERTA; END;",
        )
        self.assertEqual(
            cambios,
            [("GPS_CERO_HOY_ADV", Decimal("3"), "CLASIFICACION")],
        )
        conexion.rollback.assert_not_called()
        conexion.cursor.return_value.__exit__.assert_called_once()
        mock_conexion.return_value.__exit__.assert_called_once()

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository."
        "obtener_conexion_oracle"
    )
    def test_sin_cambios_confirma_sin_update_ni_procedure(self, mock_conexion):
        self.mock_conexion = mock_conexion
        conexion, cursor = self.preparar_oracle(
            [("GPS_CERO_HOY_ADV", Decimal("2"), "CLASIFICACION")]
        )

        cambios = reglas_alertas_repository.actualizar_reglas(
            [("GPS_CERO_HOY_ADV", Decimal("2.00"))],
            tipos_permitidos=self.TIPOS_VALIDOS,
        )

        self.assertEqual(cambios, [])
        self.assertEqual(cursor.execute.call_count, 1)
        conexion.commit.assert_called_once_with()
        conexion.rollback.assert_not_called()

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository."
        "obtener_conexion_oracle"
    )
    def test_tipo_persistido_invalido_revierte_antes_del_update(
        self,
        mock_conexion,
    ):
        self.mock_conexion = mock_conexion
        conexion, cursor = self.preparar_oracle(
            [("GPS_CERO_HOY_ADV", Decimal("2"), "DESCONOCIDO")]
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Hay reglas con un tipo no reconocido: DESCONOCIDO",
        ):
            reglas_alertas_repository.actualizar_reglas(
                [("GPS_CERO_HOY_ADV", Decimal("3"))],
                tipos_permitidos=self.TIPOS_VALIDOS,
            )

        self.assertEqual(cursor.execute.call_count, 1)
        conexion.commit.assert_not_called()
        conexion.rollback.assert_called_once_with()

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository."
        "obtener_conexion_oracle"
    )
    def test_recalculo_conserva_procedure_commit_y_ausencia_de_rollback_explicito(
        self,
        mock_conexion,
    ):
        self.mock_conexion = mock_conexion
        conexion, cursor = self.preparar_oracle()

        reglas_alertas_repository.recalcular_alertas("completo")

        cursor.execute.assert_called_once_with(
            "BEGIN USR_LAB.PRC_RECALCULAR_ALERTAS_SEGURO; END;"
        )
        conexion.commit.assert_called_once_with()
        conexion.rollback.assert_not_called()


class ReglasAlertasServiceRepositoryDelegationTests(SimpleTestCase):
    @patch(
        "apps.dashboard.services.reglas_alertas_service."
        "reglas_alertas_repository.obtener_reglas"
    )
    def test_lectura_conserva_categorias_orden_y_contrato(self, mock_reglas):
        mock_reglas.return_value = [
            {
                "clave": clave,
                "valor_numero": Decimal("1"),
                "descripcion": None,
                "activo": 1,
                "fecha_actualizacion": None,
                "tipo_regla": "DETECCION",
            }
            for clave in reglas_alertas_service.CLAVES_PERMITIDAS_TODO
        ]

        resultado = reglas_alertas_service.obtener_reglas_alertas()

        mock_reglas.assert_called_once_with(
            sorted(reglas_alertas_service.CLAVES_PERMITIDAS_TODO)
        )
        self.assertEqual(
            [regla["clave"] for regla in resultado["GPS"]],
            reglas_alertas_service.CLAVES_PERMITIDAS["GPS"],
        )
        self.assertEqual(
            [regla["clave"] for regla in resultado["BATERIA"]],
            reglas_alertas_service.CLAVES_PERMITIDAS["BATERIA"],
        )
        self.assertTrue(
            all(
                regla["descripcion"] == ""
                for categoria in resultado.values()
                for regla in categoria
            )
        )

    @patch(
        "apps.dashboard.services.reglas_alertas_service."
        "reglas_alertas_repository.obtener_reglas",
        side_effect=RuntimeError("fallo lectura sintético"),
    )
    def test_error_lectura_conserva_runtime_error_observable(self, _mock_reglas):
        with self.assertRaisesRegex(
            RuntimeError,
            "No fue posible cargar las reglas de alertas desde Oracle: "
            "fallo lectura sintético",
        ):
            reglas_alertas_service.obtener_reglas_alertas()
