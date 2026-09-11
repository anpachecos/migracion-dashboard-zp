from contextlib import ExitStack
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.dashboard.services.gps_service import (
    LATITUD_LABORATORIO_ZP,
    LONGITUD_LABORATORIO_ZP,
    NOMBRE_LABORATORIO_ZP,
    RADIO_LABORATORIO_ZP,
    obtener_contexto_gps,
    obtener_rango_fechas_gps,
    obtener_referencia_desde_cache,
    obtener_registros_gps_oracle,
)


class GpsServiceLogicaPuraTests(SimpleTestCase):
    AHORA = datetime(2026, 9, 10, 12, 0)

    def setUp(self):
        self.factory = RequestFactory()
        self.ubicacion_vigente = {
            "AMID": "7500001",
            "NOMBRE": "Zona sintética",
            "LATITUD_ESPERADA": -33.45,
            "LONGITUD_ESPERADA": -70.66,
            "RADIO_METROS": 150,
            "OPERATIVA": 1,
            "VERSION_ZP": "VTEST",
            "ARCHIVO_ORIGEN": "ubicaciones_sinteticas.xlsx",
            "FECHA_CARGA": datetime(2026, 9, 1, 8, 0),
        }

    def registro(
        self,
        identificador,
        fecha,
        latitud,
        longitud,
        transmitio_gps=True,
    ):
        return SimpleNamespace(
            id=identificador,
            amid=7500001,
            fec_descarga=fecha,
            fec_estado=fecha,
            fecha_hora=fecha,
            fecha_registro=fecha,
            fecha_hora_anterior=None,
            transmitio_gps=transmitio_gps,
            latitud=latitud,
            longitud=longitud,
            porcentaje_bateria=75,
            is_contiene_gps=True,
            is_error_obtener_gps=False,
        )

    def contexto(self, registros, historial=None, vigente=None, distancia=None):
        request = self.factory.get("/gps/", {"amid": "7500001"})
        conexion = MagicMock()
        contexto_conexion = MagicMock()
        contexto_conexion.__enter__.return_value = conexion

        if vigente is None:
            vigente = self.ubicacion_vigente

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "apps.dashboard.services.gps_service.obtener_ahora_referencia",
                    return_value=self.AHORA,
                )
            )
            stack.enter_context(
                patch(
                    "apps.dashboard.services.gps_service.obtener_registros_gps_oracle",
                    return_value=registros,
                )
            )
            stack.enter_context(
                patch(
                    "apps.dashboard.services.gps_service.obtener_conexion_oracle",
                    return_value=contexto_conexion,
                )
            )
            stack.enter_context(
                patch(
                    "apps.dashboard.services.gps_service.obtener_historial_ubicacion_amid",
                    return_value=historial or [],
                )
            )
            stack.enter_context(
                patch(
                    "apps.dashboard.services.gps_service.obtener_ubicacion_vigente_amid",
                    return_value=vigente,
                )
            )
            if distancia is not None:
                stack.enter_context(
                    patch(
                        "apps.dashboard.services.gps_service.calcular_distancia_metros",
                        return_value=distancia,
                    )
                )

            return obtener_contexto_gps(request)

    def test_rango_predeterminado_cubre_el_dia_completo(self):
        request = self.factory.get("/gps/")

        with patch(
            "apps.dashboard.services.gps_service.obtener_ahora_referencia",
            return_value=self.AHORA,
        ):
            filtros = obtener_rango_fechas_gps(request)

        self.assertEqual(filtros["fecha_inicio"], datetime(2026, 9, 10, 0, 0))
        self.assertEqual(filtros["fecha_fin"], datetime(2026, 9, 11, 0, 0))
        self.assertEqual(filtros["hora_desde"], "00:00")
        self.assertEqual(filtros["hora_hasta"], "23:30")

    def test_rango_invertido_vuelve_al_rango_predeterminado(self):
        request = self.factory.get(
            "/gps/",
            {
                "fecha_desde": "2026-09-11",
                "fecha_hasta": "2026-09-10",
                "hora_desde": "18:00",
                "hora_hasta": "08:00",
            },
        )

        with patch(
            "apps.dashboard.services.gps_service.obtener_ahora_referencia",
            return_value=self.AHORA,
        ):
            filtros = obtener_rango_fechas_gps(request)

        self.assertEqual(filtros["fecha_inicio"], datetime(2026, 9, 10, 0, 0))
        self.assertEqual(filtros["fecha_fin"], datetime(2026, 9, 11, 0, 0))
        self.assertEqual(filtros["fecha_desde_input"], "2026-09-10")
        self.assertEqual(filtros["fecha_hasta_input"], "2026-09-10")

    @patch("apps.dashboard.services.gps_service.obtener_conexion_oracle")
    def test_fecha_hora_repetida_anula_coordenadas_del_bloque(
        self,
        mock_conexion,
    ):
        cursor = mock_conexion.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (datetime(2026, 9, 10, 7, 30),)
        cursor.description = [
            ("ID",),
            ("AMID",),
            ("FEC_DESCARGA",),
            ("FEC_ESTADO",),
            ("FECHA_HORA",),
            ("FECHA_REGISTRO",),
            ("LATITUD",),
            ("LONGITUD",),
            ("PORCENTAJE_BATERIA",),
            ("IS_CONTIENE_GPS",),
            ("IS_ERROR_OBTENER_GPS",),
        ]
        fecha_reportada = datetime(2026, 9, 10, 8, 0)
        cursor.fetchall.return_value = [
            (
                1,
                7500001,
                fecha_reportada,
                fecha_reportada,
                fecha_reportada,
                datetime(2026, 9, 10, 8, 0),
                -33.45,
                -70.66,
                80,
                1,
                0,
            ),
            (
                2,
                7500001,
                fecha_reportada,
                fecha_reportada,
                fecha_reportada,
                datetime(2026, 9, 10, 8, 30),
                -33.46,
                -70.67,
                79,
                1,
                0,
            ),
        ]

        registros = obtener_registros_gps_oracle(
            amid="7500001",
            fecha_inicio=datetime(2026, 9, 10, 8, 0),
            fecha_fin=datetime(2026, 9, 10, 9, 0),
        )

        self.assertTrue(registros[0].transmitio_gps)
        self.assertEqual(registros[0].latitud, -33.45)
        self.assertFalse(registros[1].transmitio_gps)
        self.assertIsNone(registros[1].latitud)
        self.assertIsNone(registros[1].longitud)

    def test_gps_cero_cuenta_como_reportado(self):
        registro_cero = self.registro(
            1,
            datetime(2026, 9, 10, 9, 0),
            0,
            0,
        )

        contexto = self.contexto([registro_cero])

        self.assertEqual(contexto["resumen_gps"]["registros_gps_reportados_periodo"], 1)
        self.assertEqual(contexto["resumen_gps"]["registros_gps_cero_periodo"], 1)
        self.assertEqual(contexto["resumen_gps"]["registros_periodo"], 1)

    def test_gps_cero_no_se_considera_fuera_de_radio(self):
        registro_cero = self.registro(
            1,
            datetime(2026, 9, 10, 9, 0),
            0,
            0,
        )

        contexto = self.contexto([registro_cero])

        self.assertEqual(contexto["resumen_gps"]["registros_fuera_periodo"], 0)
        self.assertIsNone(contexto["ubicacion_esperada"]["dentro_radio"])
        self.assertTrue(contexto["ubicacion_esperada"]["ultima_reportada_es_cero"])

    def test_gps_cero_no_centra_el_mapa(self):
        registro_cero = self.registro(
            1,
            datetime(2026, 9, 10, 9, 0),
            0,
            0,
        )

        contexto = self.contexto([registro_cero])

        self.assertIsNone(contexto["latitud"])
        self.assertIsNone(contexto["longitud"])

    def test_ultima_coordenada_valida_centra_el_mapa(self):
        registros = [
            self.registro(1, datetime(2026, 9, 10, 8, 0), -33.45, -70.66),
            self.registro(2, datetime(2026, 9, 10, 9, 0), 0, 0),
        ]

        contexto = self.contexto(registros)

        self.assertEqual(contexto["latitud"], -33.45)
        self.assertEqual(contexto["longitud"], -70.66)

    def test_ultimo_punto_reportado_define_el_estado_actual(self):
        registros = [
            self.registro(1, datetime(2026, 9, 10, 8, 0), -33.45, -70.66),
            self.registro(2, datetime(2026, 9, 10, 9, 0), 0, 0),
        ]

        contexto = self.contexto(registros)

        self.assertEqual(contexto["ultimo_registro"].id, 2)
        self.assertEqual(
            contexto["resumen_gps"]["texto_ultima_ubicacion"],
            "10-09-2026 09:00",
        )
        self.assertTrue(contexto["ubicacion_esperada"]["ultima_reportada_es_cero"])

    def test_referencia_historica_prevalece_en_su_periodo(self):
        historial = [
            {
                "NOMBRE": "Ubicación histórica sintética",
                "LATITUD_ESPERADA": -33.40,
                "LONGITUD_ESPERADA": -70.60,
                "RADIO_METROS": 120,
                "OPERATIVA": 1,
                "ORIGEN_UBICACION": "excel",
                "VERSION_ZP": "VANTERIOR",
                "FECHA_INICIO_VIGENCIA": datetime(2026, 8, 1, 0, 0),
                "FECHA_FIN_VIGENCIA": datetime(2026, 9, 1, 0, 0),
            }
        ]

        referencia = obtener_referencia_desde_cache(
            fecha_consulta=datetime(2026, 8, 15, 12, 0),
            historial_amid=historial,
            vigente_amid=self.ubicacion_vigente,
        )

        self.assertEqual(referencia["nombre"], "Ubicación histórica sintética")
        self.assertEqual(referencia["origen_ubicacion"], "excel")
        self.assertEqual(referencia["version_zp"], "VANTERIOR")

    def test_sin_historial_usa_ubicacion_vigente(self):
        referencia = obtener_referencia_desde_cache(
            fecha_consulta=datetime(2026, 9, 10, 9, 0),
            historial_amid=[],
            vigente_amid=self.ubicacion_vigente,
        )

        self.assertEqual(referencia["nombre"], "Zona sintética")
        self.assertEqual(referencia["origen_ubicacion"], "vigente")
        self.assertTrue(referencia["operativa"])

    def test_sin_ubicacion_usa_laboratorio(self):
        referencia = obtener_referencia_desde_cache(
            fecha_consulta=datetime(2026, 9, 10, 9, 0),
            historial_amid=[],
            vigente_amid=None,
        )

        self.assertEqual(referencia["nombre"], NOMBRE_LABORATORIO_ZP)
        self.assertEqual(referencia["latitud"], LATITUD_LABORATORIO_ZP)
        self.assertEqual(referencia["longitud"], LONGITUD_LABORATORIO_ZP)
        self.assertEqual(referencia["radio_metros"], RADIO_LABORATORIO_ZP)
        self.assertEqual(referencia["origen_ubicacion"], "laboratorio_default")
        self.assertFalse(referencia["operativa"])

    def test_distancia_igual_al_radio_cuenta_como_dentro(self):
        registro = self.registro(
            1,
            datetime(2026, 9, 10, 9, 0),
            -33.45,
            -70.66,
        )

        contexto = self.contexto([registro], distancia=150)

        self.assertEqual(contexto["resumen_gps"]["registros_dentro_periodo"], 1)
        self.assertEqual(contexto["resumen_gps"]["registros_fuera_periodo"], 0)
        self.assertTrue(contexto["ubicacion_esperada"]["dentro_radio"])
