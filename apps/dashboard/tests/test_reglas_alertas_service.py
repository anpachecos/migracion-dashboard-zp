from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.dashboard.services.reglas_alertas_service import (
    actualizar_reglas_alertas,
    recalcular_alertas,
    usuario_puede_editar_reglas,
)


class ReglasAlertasServiceTests(SimpleTestCase):
    def test_usuario_puede_editar_reglas_accepts_superuser(self):
        """
        Un superusuario puede editar reglas de alertas.
        """

        user = SimpleNamespace(is_superuser=True)

        self.assertTrue(usuario_puede_editar_reglas(user))

    def test_usuario_puede_editar_reglas_accepts_admin_group(self):
        """
        Un usuario del grupo Admin puede editar reglas de alertas.
        """

        class GrupoAdmin:
            def filter(self, name):
                self.name = name
                return self

            def exists(self):
                return self.name == "Admin"

        user = SimpleNamespace(is_superuser=False, groups=GrupoAdmin())

        self.assertTrue(usuario_puede_editar_reglas(user))

    def test_usuario_puede_editar_reglas_rejects_non_admin(self):
        """
        Un usuario que no es superusuario ni pertenece al grupo Admin
        no puede editar reglas.
        """

        class GrupoNoAdmin:
            def filter(self, name):
                self.name = name
                return self

            def exists(self):
                return False

        user = SimpleNamespace(is_superuser=False, groups=GrupoNoAdmin())

        self.assertFalse(usuario_puede_editar_reglas(user))

    def test_actualizar_reglas_alertas_rejects_unknown_keys(self):
        """
        No se deben aceptar claves de reglas que no estén permitidas.
        """

        with self.assertRaises(ValueError):
            actualizar_reglas_alertas({"regla_CLAVE_DESCONOCIDA": "3"})

    def _preparar_oracle(self, filas):
        conexion = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = filas
        cursor.rowcount = 1
        conexion.cursor.return_value.__enter__.return_value = cursor

        contexto_conexion = MagicMock()
        contexto_conexion.__enter__.return_value = conexion
        return contexto_conexion, conexion, cursor

    def test_actualizar_reglas_alertas_omite_valores_sin_cambios(self):
        contexto, conexion, cursor = self._preparar_oracle(
            [("GPS_CERO_HOY_ADV", Decimal("2"), "CLASIFICACION")]
        )

        with patch(
            "apps.core.oracle.connection.obtener_conexion_oracle",
            return_value=contexto,
        ):
            resultado = actualizar_reglas_alertas(
                {"regla_GPS_CERO_HOY_ADV": "2.00"}
            )

        self.assertEqual(
            resultado,
            {"cantidad": 0, "claves": [], "modo_recalculo": None},
        )
        self.assertEqual(cursor.execute.call_count, 1)
        conexion.commit.assert_called_once()
        conexion.rollback.assert_not_called()

    def test_actualizar_clasificacion_solicita_recalculo_rapido(self):
        contexto, conexion, cursor = self._preparar_oracle(
            [("GPS_CERO_HOY_ADV", Decimal("2"), "CLASIFICACION")]
        )

        with patch(
            "apps.core.oracle.connection.obtener_conexion_oracle",
            return_value=contexto,
        ):
            resultado = actualizar_reglas_alertas(
                {"regla_GPS_CERO_HOY_ADV": "3"}
            )

        self.assertEqual(resultado["cantidad"], 1)
        self.assertEqual(resultado["claves"], ["GPS_CERO_HOY_ADV"])
        self.assertEqual(resultado["modo_recalculo"], "rapido")
        self.assertIn(
            "PRC_VALIDAR_REGLAS_ALERTA",
            cursor.execute.call_args_list[-1].args[0],
        )
        conexion.commit.assert_called_once()

    def test_actualizar_deteccion_solicita_recalculo_completo(self):
        contexto, _conexion, _cursor = self._preparar_oracle(
            [("BAT_CAIDA_MIN_DETECTAR", Decimal("20"), "DETECCION")]
        )

        with patch(
            "apps.core.oracle.connection.obtener_conexion_oracle",
            return_value=contexto,
        ):
            resultado = actualizar_reglas_alertas(
                {"regla_BAT_CAIDA_MIN_DETECTAR": "21"}
            )

        self.assertEqual(resultado["modo_recalculo"], "completo")

    def test_recalcular_alertas_usa_wrapper_segun_modo(self):
        contexto, _conexion, cursor = self._preparar_oracle([])

        with patch(
            "apps.core.oracle.connection.obtener_conexion_oracle",
            return_value=contexto,
        ):
            recalcular_alertas(modo_recalculo="rapido")

        cursor.execute.assert_called_once_with(
            "BEGIN USR_LAB.PRC_RECLASIFICAR_ALERTAS; END;"
        )

    def test_recalcular_alertas_rechaza_modo_desconocido(self):
        with self.assertRaises(ValueError):
            recalcular_alertas(modo_recalculo="desconocido")
