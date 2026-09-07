from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.dashboard.services.ubicaciones_service import (
    sincronizar_amids_ubicaciones_oracle,
)


class SincronizarAmidsUbicacionesTests(SimpleTestCase):
    @patch(
        "apps.dashboard.services.ubicaciones_service.obtener_conexion_oracle"
    )
    def test_invoca_procedimiento_y_devuelve_validacion(self, mock_conexion):
        conexion = mock_conexion.return_value.__enter__.return_value
        cursor = conexion.cursor.return_value.__enter__.return_value
        ubicaciones_var = MagicMock()
        historiales_var = MagicMock()
        ubicaciones_var.getvalue.return_value = 2
        historiales_var.getvalue.return_value = 2
        cursor.var.side_effect = [ubicaciones_var, historiales_var]
        cursor.fetchone.return_value = (0, 0)

        resultado = sincronizar_amids_ubicaciones_oracle()

        cursor.callproc.assert_called_once_with(
            "USR_LAB.PRC_SINC_UBIC_AMID",
            [ubicaciones_var, historiales_var],
        )
        self.assertEqual(
            resultado,
            {
                "ubicaciones_creadas": 2,
                "historiales_creados": 2,
                "sin_ubicacion": 0,
                "sin_historial_abierto": 0,
            },
        )
