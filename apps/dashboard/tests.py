from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.dashboard.context_processors import (
    CACHE_MISS,
    datos_actualizacion_dashboard,
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
