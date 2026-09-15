from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.dashboard.services.reglas_alertas_service import (
    actualizar_reglas_alertas,
    recalcular_alertas,
)


class ReglasAlertasTransaccionCaracterizacionTests(SimpleTestCase):
    CLAVE = "GPS_CERO_HOY_ADV"

    def preparar_oracle(self, filas, rowcount=1):
        conexion = MagicMock(name="conexion_oracle_falsa")
        cursor = MagicMock(name="cursor_oracle_falso")
        cursor.fetchall.return_value = filas
        cursor.rowcount = rowcount
        conexion.cursor.return_value.__enter__.return_value = cursor

        contexto = MagicMock(name="contexto_oracle_falso")
        contexto.__enter__.return_value = conexion
        return contexto, conexion, cursor

    def formulario(self, valor="3"):
        return {f"regla_{self.CLAVE}": valor}

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository.obtener_conexion_oracle"
    )
    def test_regla_inexistente_revierte_y_propaga_error(self, mock_conexion):
        contexto, conexion, cursor = self.preparar_oracle([])
        mock_conexion.return_value = contexto

        with self.assertRaisesRegex(
            RuntimeError,
            f"No existen en Oracle las reglas: {self.CLAVE}",
        ):
            actualizar_reglas_alertas(self.formulario())

        self.assertEqual(cursor.execute.call_count, 1)
        self.assertIn("FOR UPDATE", cursor.execute.call_args.args[0])
        conexion.commit.assert_not_called()
        conexion.rollback.assert_called_once_with()

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository.obtener_conexion_oracle"
    )
    def test_fallo_select_for_update_revierte_y_propaga(self, mock_conexion):
        contexto, conexion, cursor = self.preparar_oracle([])
        cursor.execute.side_effect = RuntimeError("fallo select sintético")
        mock_conexion.return_value = contexto

        with self.assertRaisesRegex(RuntimeError, "fallo select sintético"):
            actualizar_reglas_alertas(self.formulario())

        conexion.commit.assert_not_called()
        conexion.rollback.assert_called_once_with()

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository.obtener_conexion_oracle"
    )
    def test_update_sin_fila_revierte_y_propaga_error(self, mock_conexion):
        contexto, conexion, cursor = self.preparar_oracle(
            [(self.CLAVE, Decimal("2"), "CLASIFICACION")],
            rowcount=0,
        )
        mock_conexion.return_value = contexto

        with self.assertRaisesRegex(
            RuntimeError,
            f"No se pudo actualizar la regla {self.CLAVE}",
        ):
            actualizar_reglas_alertas(self.formulario())

        self.assertEqual(cursor.execute.call_count, 2)
        conexion.commit.assert_not_called()
        conexion.rollback.assert_called_once_with()

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository.obtener_conexion_oracle"
    )
    def test_excepcion_durante_update_revierte_y_propaga(self, mock_conexion):
        contexto, conexion, cursor = self.preparar_oracle(
            [(self.CLAVE, Decimal("2"), "CLASIFICACION")]
        )

        def ejecutar(query, *_args):
            if query.lstrip().startswith("UPDATE"):
                raise RuntimeError("fallo update sintético")

        cursor.execute.side_effect = ejecutar
        mock_conexion.return_value = contexto

        with self.assertRaisesRegex(RuntimeError, "fallo update sintético"):
            actualizar_reglas_alertas(self.formulario())

        conexion.commit.assert_not_called()
        conexion.rollback.assert_called_once_with()

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository.obtener_conexion_oracle"
    )
    def test_fallo_procedure_validacion_revierte_y_no_confirma(
        self,
        mock_conexion,
    ):
        contexto, conexion, cursor = self.preparar_oracle(
            [(self.CLAVE, Decimal("2"), "CLASIFICACION")]
        )

        def ejecutar(query, *_args):
            if "PRC_VALIDAR_REGLAS_ALERTA" in query:
                raise RuntimeError("fallo procedure sintético")

        cursor.execute.side_effect = ejecutar
        mock_conexion.return_value = contexto

        with self.assertRaisesRegex(RuntimeError, "fallo procedure sintético"):
            actualizar_reglas_alertas(self.formulario())

        conexion.commit.assert_not_called()
        conexion.rollback.assert_called_once_with()

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository.obtener_conexion_oracle"
    )
    def test_orden_transaccional_select_update_validacion_commit(
        self,
        mock_conexion,
    ):
        contexto, conexion, cursor = self.preparar_oracle(
            [(self.CLAVE, Decimal("2"), "CLASIFICACION")]
        )
        eventos = []

        def ejecutar(query, *_args):
            if "FOR UPDATE" in query:
                eventos.append("SELECT_FOR_UPDATE")
            elif query.lstrip().startswith("UPDATE"):
                eventos.append("UPDATE")
            elif "PRC_VALIDAR_REGLAS_ALERTA" in query:
                eventos.append("PRC_VALIDAR")

        cursor.execute.side_effect = ejecutar
        conexion.commit.side_effect = lambda: eventos.append("COMMIT")
        conexion.rollback.side_effect = lambda: eventos.append("ROLLBACK")
        mock_conexion.return_value = contexto

        resultado = actualizar_reglas_alertas(self.formulario())

        self.assertEqual(
            eventos,
            ["SELECT_FOR_UPDATE", "UPDATE", "PRC_VALIDAR", "COMMIT"],
        )
        self.assertEqual(
            resultado,
            {
                "cantidad": 1,
                "claves": [self.CLAVE],
                "modo_recalculo": "rapido",
            },
        )
        conexion.rollback.assert_not_called()

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository.obtener_conexion_oracle"
    )
    def test_recalculo_con_fallo_no_confirma_y_propaga_runtime_error(
        self,
        mock_conexion,
    ):
        contexto, conexion, cursor = self.preparar_oracle([])
        cursor.execute.side_effect = RuntimeError("fallo recálculo sintético")
        mock_conexion.return_value = contexto

        with self.assertRaisesRegex(
            RuntimeError,
            "No se pudo recalcular alertas después de",
        ):
            recalcular_alertas(modo_recalculo="rapido")

        conexion.commit.assert_not_called()
        conexion.rollback.assert_not_called()
