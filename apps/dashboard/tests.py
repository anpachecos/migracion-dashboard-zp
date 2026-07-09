from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.dashboard.context_processors import (
    CACHE_MISS,
    datos_actualizacion_dashboard,
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
