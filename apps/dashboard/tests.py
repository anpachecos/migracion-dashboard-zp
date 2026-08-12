from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.dashboard.context_processors import datos_actualizacion_dashboard
from apps.dashboard.services.alertas_service import (
    calcular_estado_estatus,
    construir_condicion_problema,
)
from apps.dashboard.services.reglas_alertas_service import (
    actualizar_reglas_alertas,
    recalcular_alertas,
    usuario_puede_editar_reglas,
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
            context = datos_actualizacion_dashboard(request)

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
            context = datos_actualizacion_dashboard(request)

        self.assertIn("ultima_actualizacion_dashboard", context)
        self.assertEqual(context["ultima_carga_datos"], ultima_carga)
        self.assertEqual(context["ultima_actualizacion_version_zp"], ultima_version)

        mock_ultima_carga.assert_called_once()
        mock_ultima_version.assert_called_once()


class AlertasServiceTests(SimpleTestCase):
    def test_construir_condicion_problema_maps_known_values(self):
        """
        Verifica que los filtros visibles del panel de alertas se traduzcan
        a condiciones SQL esperadas.
        """

        self.assertEqual(
            construir_condicion_problema("bateria_caida"),
            "CAIDAS_HOY > 0 OR CAIDAS_HIST > 0",
        )

        self.assertEqual(
            construir_condicion_problema("ambos"),
            "NIVEL_ALERTA_GPS <> 'OK' AND NIVEL_ALERTA_BATERIA <> 'OK'",
        )

    def test_calcular_estado_estatus_classifies_statuses(self):
        """
        Verifica la clasificación visual del último estatus:
        - sin estatus;
        - estatus antiguo;
        - estatus reciente.
        """

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
            "apps.dashboard.services.reglas_alertas_service.obtener_conexion_oracle",
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
            "apps.dashboard.services.reglas_alertas_service.obtener_conexion_oracle",
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
            "apps.dashboard.services.reglas_alertas_service.obtener_conexion_oracle",
            return_value=contexto,
        ):
            resultado = actualizar_reglas_alertas(
                {"regla_BAT_CAIDA_MIN_DETECTAR": "21"}
            )

        self.assertEqual(resultado["modo_recalculo"], "completo")

    def test_recalcular_alertas_usa_wrapper_segun_modo(self):
        contexto, _conexion, cursor = self._preparar_oracle([])

        with patch(
            "apps.dashboard.services.reglas_alertas_service.obtener_conexion_oracle",
            return_value=contexto,
        ):
            recalcular_alertas(modo_recalculo="rapido")

        cursor.execute.assert_called_once_with(
            "BEGIN USR_LAB.PRC_RECLASIFICAR_ALERTAS; END;"
        )

    def test_recalcular_alertas_rechaza_modo_desconocido(self):
        with self.assertRaises(ValueError):
            recalcular_alertas(modo_recalculo="desconocido")
