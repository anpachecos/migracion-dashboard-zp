from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.dashboard import context_processors


class ContextProcessorsOracleTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @patch(
        "apps.dashboard.context_processors.estado_dashboard_repository."
        "obtener_ultima_carga_datos"
    )
    def test_ultima_carga_respeta_cache_sin_consultar_repository(
        self,
        mock_ultima_carga,
    ):
        esperado = datetime(2026, 9, 14, 10, 0)
        cache.set(context_processors.CACHE_KEY_ULTIMA_CARGA_DATOS, esperado, 300)

        resultado = context_processors.obtener_ultima_carga_datos_oracle()

        self.assertEqual(resultado, esperado)
        mock_ultima_carga.assert_not_called()

    @patch(
        "apps.dashboard.context_processors.estado_dashboard_repository."
        "obtener_ultima_carga_datos"
    )
    def test_ultima_carga_normaliza_fecha_y_conserva_ttl(
        self,
        mock_ultima_carga,
    ):
        fecha_aware = datetime(
            2026,
            9,
            14,
            10,
            0,
            tzinfo=datetime_timezone.utc,
        )
        mock_ultima_carga.return_value = (fecha_aware,)

        with patch("apps.dashboard.context_processors.cache.set") as mock_cache_set:
            resultado = context_processors.obtener_ultima_carga_datos_oracle()

        self.assertEqual(resultado, datetime(2026, 9, 14, 7, 0))
        mock_cache_set.assert_called_once_with(
            context_processors.CACHE_KEY_ULTIMA_CARGA_DATOS,
            resultado,
            context_processors.CACHE_TIMEOUT_SEGUNDOS,
        )

    @patch(
        "apps.dashboard.context_processors.estado_dashboard_repository."
        "obtener_ultima_version_zp",
        side_effect=RuntimeError("fallo sintético"),
    )
    def test_ultima_version_con_error_conserva_log_fallback_y_cache(
        self,
        _mock_ultima_version,
    ):
        with patch(
            "apps.dashboard.context_processors.logger.exception"
        ) as mock_log, patch(
            "apps.dashboard.context_processors.cache.set"
        ) as mock_cache_set:
            resultado = context_processors.obtener_ultima_version_zp_oracle()

        self.assertIsNone(resultado)
        mock_log.assert_called_once()
        mock_cache_set.assert_called_once_with(
            context_processors.CACHE_KEY_ULTIMA_VERSION_ZP,
            None,
            context_processors.CACHE_TIMEOUT_SEGUNDOS,
        )
