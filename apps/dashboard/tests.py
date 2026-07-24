from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.dashboard.context_processors import (
    CACHE_MISS,
    datos_actualizacion_dashboard,
)
from apps.dashboard.services.alertas_service import (
    calcular_estado_estatus,
    construir_condicion_problema,
)
from apps.dashboard.services.reglas_alertas_service import (
    actualizar_reglas_alertas,
    usuario_puede_editar_reglas,
)


class ContextProcessorTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("apps.dashboard.context_processors._iniciar_precarga_datos_actualizacion")
    def test_authenticated_request_starts_background_warmup_when_cache_is_empty(self, mock_precarga):
        request = self.factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True)

        with patch("apps.dashboard.context_processors.cache.get", side_effect=[CACHE_MISS, CACHE_MISS]):
            context = datos_actualizacion_dashboard(request)

        self.assertIn("ultima_actualizacion_dashboard", context)
        self.assertIsNone(context["ultima_carga_datos"])
        self.assertIsNone(context["ultima_actualizacion_version_zp"])
        mock_precarga.assert_called_once()


class AlertasServiceTests(SimpleTestCase):
    def test_construir_condicion_problema_maps_known_values(self):
        self.assertEqual(
            construir_condicion_problema("bateria_caida"),
            "CAIDAS_HOY > 0 OR CAIDAS_HIST > 0",
        )
        self.assertEqual(
            construir_condicion_problema("ambos"),
            "NIVEL_ALERTA_GPS <> 'OK' AND NIVEL_ALERTA_BATERIA <> 'OK'",
        )

    def test_calcular_estado_estatus_classifies_statuses(self):
        self.assertEqual(
            calcular_estado_estatus(None),
            {
                "estado_estatus": "sin_estatus",
                "texto_estatus": "Sin estatus",
                "clase_estatus": "estatus-sin",
            },
        )

        antigua = datetime.now() - timedelta(hours=2)
        self.assertEqual(
            calcular_estado_estatus(antigua),
            {
                "estado_estatus": "estatus_antiguo",
                "texto_estatus": "Hace más de 1 hora",
                "clase_estatus": "estatus-antiguo",
            },
        )

        reciente = datetime.now() - timedelta(minutes=10)
        self.assertEqual(
            calcular_estado_estatus(reciente),
            {
                "estado_estatus": "con_estatus",
                "texto_estatus": "Con estatus",
                "clase_estatus": "estatus-ok",
            },
        )


class ReglasAlertasServiceTests(SimpleTestCase):
    def test_usuario_puede_editar_reglas_accepts_admin_group(self):
        class GrupoAdmin:
            def filter(self, name):
                self.name = name
                return self

            def exists(self):
                return self.name == "Admin"

        user = SimpleNamespace(is_superuser=False, groups=GrupoAdmin())

        self.assertTrue(usuario_puede_editar_reglas(user))

    def test_actualizar_reglas_alertas_rejects_unknown_keys(self):
        with self.assertRaises(ValueError):
            actualizar_reglas_alertas({"regla_CLAVE_DESCONOCIDA": "3"})
