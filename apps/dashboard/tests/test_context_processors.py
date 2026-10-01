from datetime import datetime, timedelta, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from django.conf import settings

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


class ContextProcessorTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_anonymous_request_does_not_query_oracle(self):
        """
        Si el usuario no está autenticado, el context processor no debe consultar Oracle.
        Esto evita lentitud innecesaria en login/logout.
        """

        request = self.factory.get("/")
        request.user = SimpleNamespace(is_authenticated=False)

        with patch(
            "apps.dashboard.context_processors.obtener_ultima_carga_datos_oracle"
        ) as mock_ultima_carga, patch(
            "apps.dashboard.context_processors.obtener_ultima_version_zp_oracle"
        ) as mock_ultima_version:
            context = context_processors.datos_actualizacion_dashboard(request)

        self.assertEqual(context, {})
        mock_ultima_carga.assert_not_called()
        mock_ultima_version.assert_not_called()

    def test_authenticated_request_returns_sidebar_context(self):
        """
        Si el usuario está autenticado, el context processor debe devolver
        las variables globales usadas por el sidebar.
        """

        request = self.factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True)

        ultima_carga = datetime(2026, 8, 7, 9, 30)
        ultima_version = datetime(2026, 8, 7, 8, 0)

        with patch(
            "apps.dashboard.context_processors.obtener_ultima_carga_datos_oracle",
            return_value=ultima_carga,
        ) as mock_ultima_carga, patch(
            "apps.dashboard.context_processors.obtener_ultima_version_zp_oracle",
            return_value=ultima_version,
        ) as mock_ultima_version:
            context = context_processors.datos_actualizacion_dashboard(request)

        self.assertEqual(context["ultima_carga_datos"], ultima_carga)
        self.assertEqual(context["ultima_actualizacion_version_zp"], ultima_version)
        self.assertIn("estado_carga_datos", context)
        self.assertIn("estado_version_zp", context)

        mock_ultima_carga.assert_called_once()
        mock_ultima_version.assert_called_once()

    def test_ya_no_expone_la_hora_de_render(self):
        """
        `ultima_actualizacion_dashboard` era timezone.now() en cada render:
        cambiaba en cada recarga sin representar nada. No debe volver.
        """

        request = self.factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True)

        with patch(
            "apps.dashboard.context_processors.obtener_ultima_carga_datos_oracle",
            return_value=None,
        ), patch(
            "apps.dashboard.context_processors.obtener_ultima_version_zp_oracle",
            return_value=None,
        ):
            context = context_processors.datos_actualizacion_dashboard(request)

        self.assertNotIn("ultima_actualizacion_dashboard", context)


class EstadoFrescuraTests(SimpleTestCase):
    """
    El semáforo del sidebar se decide por antigüedad de los datos. Estos
    cortes son la política visible para el usuario, por eso se fijan.
    """

    def test_sin_datos_es_estado_propio_y_no_error(self):
        estado = context_processors.estado_frescura(
            None,
            ahora=datetime(2026, 9, 14, 10, 0, tzinfo=datetime_timezone.utc),
        )

        self.assertEqual(estado["estado"], "sin-datos")
        self.assertEqual(estado["texto"], "Sin datos")
        self.assertIsNone(estado["epoch"])

    def test_reciente_esta_ok(self):
        ahora = datetime(2026, 9, 14, 10, 0, tzinfo=datetime_timezone.utc)
        estado = context_processors.estado_frescura(
            ahora - timedelta(minutes=10),
            ahora=ahora,
        )

        self.assertEqual(estado["estado"], "ok")
        self.assertEqual(estado["texto"], "hace 10 min")

    def test_umbral_de_aviso_dispara_amarelo(self):
        ahora = datetime(2026, 9, 14, 10, 0, tzinfo=datetime_timezone.utc)
        estado = context_processors.estado_frescura(
            ahora - timedelta(minutes=75),
            ahora=ahora,
        )

        self.assertEqual(estado["estado"], "aviso")
        self.assertEqual(estado["texto"], "hace 1 h")

    def test_umbral_de_error_dispara_rojo(self):
        ahora = datetime(2026, 9, 14, 10, 0, tzinfo=datetime_timezone.utc)
        estado = context_processors.estado_frescura(
            ahora - timedelta(hours=5),
            ahora=ahora,
        )

        self.assertEqual(estado["estado"], "error")
        self.assertEqual(estado["texto"], "hace 5 h")

    def test_texto_en_dias_cuando_pasa_la_jornada(self):
        ahora = datetime(2026, 9, 14, 10, 0, tzinfo=datetime_timezone.utc)
        estado = context_processors.estado_frescura(
            ahora - timedelta(days=3),
            ahora=ahora,
        )

        self.assertEqual(estado["texto"], "hace 3 días")

    def test_acepta_fecha_naive_que_ya_viene_en_hora_local(self):
        """
        Las fechas de Oracle llegan sin zona horaria y ya convertidas a hora
        local. Si se trataran como UTC el texto salría corrido 3 horas.
        """

        ahora = datetime(2026, 9, 14, 10, 0, tzinfo=datetime_timezone.utc)
        estado = context_processors.estado_frescura(
            datetime(2026, 9, 14, 7, 0),
            ahora=ahora,
        )

        self.assertEqual(estado["texto"], "hace instantes")
        self.assertEqual(estado["estado"], "ok")


    def test_reloj_en_el_futuro_no_produce_texto_negativo(self):
        ahora = datetime(2026, 9, 14, 10, 0, tzinfo=datetime_timezone.utc)
        estado = context_processors.estado_frescura(
            ahora + timedelta(hours=2),
            ahora=ahora,
        )

        self.assertEqual(estado["texto"], "hace instantes")
        self.assertEqual(estado["estado"], "ok")

    def test_expone_epoch_para_que_el_navegador_no_repita_la_politica(self):
        ahora = datetime(2026, 9, 14, 10, 0, tzinfo=datetime_timezone.utc)
        estado = context_processors.estado_frescura(
            ahora - timedelta(minutes=5),
            ahora=ahora,
        )

        self.assertEqual(estado["epoch"], int(ahora.timestamp()) - 300)
        self.assertEqual(estado["umbral_aviso"], context_processors.UMBRAL_AVISO_MINUTOS)
        self.assertEqual(estado["umbral_error"], context_processors.UMBRAL_ERROR_MINUTOS)


class MetadatosAppTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, usuario):
        request = self.factory.get("/")
        request.user = usuario
        return request

    def test_anonymous_recibe_version_ambiente_sin_identidad(self):
        """
        El login también muestra versión y ambiente, así que el processor
        tiene que responder sin sesión. La identidad sí exige usuario.
        """

        request = self._request(SimpleNamespace(is_authenticated=False))

        contexto = context_processors.metadatos_app(request)

        self.assertEqual(contexto["VERSION_APP"], settings.VERSION_APP)
        self.assertEqual(contexto["AMBIENTE"], settings.AMBIENTE)
        self.assertNotIn("usuario_nombre", contexto)

    def test_superusuario_se_etiqueta_como_admin(self):
        request = self._request(
            SimpleNamespace(
                is_authenticated=True,
                is_superuser=True,
                get_full_name=lambda: "Antonia Pacheco",
                get_username=lambda: "apacheco",
                groups=SimpleNamespace(values_list=lambda *args, **kwargs: []),
            )
        )

        contexto = context_processors.metadatos_app(request)

        self.assertEqual(contexto["usuario_nombre"], "Antonia Pacheco")
        self.assertEqual(contexto["usuario_rol"], "Admin")
        self.assertEqual(contexto["usuario_iniciales"], "AP")

    def test_rol_toma_los_grupos_del_usuario(self):
        request = self._request(
            SimpleNamespace(
                is_authenticated=True,
                is_superuser=False,
                get_full_name=lambda: "",
                get_username=lambda: "jsonda",
                groups=SimpleNamespace(
                    values_list=lambda *args, **kwargs: ["SONDA", "Operacion"]
                ),
            )
        )

        contexto = context_processors.metadatos_app(request)

        self.assertEqual(contexto["usuario_nombre"], "jsonda")
        self.assertEqual(contexto["usuario_rol"], "SONDA, Operacion")

    def test_usuario_sin_grupos_arroba_sin_rol(self):
        request = self._request(
            SimpleNamespace(
                is_authenticated=True,
                is_superuser=False,
                get_full_name=lambda: "",
                get_username=lambda: "lector",
                groups=SimpleNamespace(values_list=lambda *args, **kwargs: []),
            )
        )

        contexto = context_processors.metadatos_app(request)

        self.assertEqual(contexto["usuario_rol"], "Sin rol")
        self.assertEqual(contexto["usuario_iniciales"], "LE")

    def test_ambiente_de_produccion_no_muestra_badge(self):
        with override_settings(AMBIENTE="PRODUCCION"):
            contexto = context_processors.metadatos_app(
                self._request(SimpleNamespace(is_authenticated=False))
            )

        self.assertFalse(contexto["ambiente_es_preproduccion"])
        self.assertEqual(contexto["ambiente_etiqueta"], "")

    def test_preproduccion_muestra_badge(self):
        with override_settings(AMBIENTE="PRE"):
            contexto = context_processors.metadatos_app(
                self._request(SimpleNamespace(is_authenticated=False))
            )

        self.assertTrue(contexto["ambiente_es_preproduccion"])
        self.assertEqual(contexto["ambiente_etiqueta"], "PREPRODUCCIÓN")

