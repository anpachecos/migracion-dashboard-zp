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
from apps.dashboard.services.horarios_zp_service import crear_configuracion_horario_zp


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
                    "apps.dashboard.services.gps_service.obtener_datos_ubicacion_amid_oracle",
                    return_value=(historial or [], vigente),
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

    @patch("apps.dashboard.repositories.gps_repository.obtener_conexion_oracle")
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


class GpsServiceContextoTests(SimpleTestCase):
    AHORA = datetime(2026, 9, 10, 12, 0)

    def setUp(self):
        self.factory = RequestFactory()
        self.vigente = {
            "AMID": "7500001",
            "NOMBRE": "Zona sintética",
            "LATITUD_ESPERADA": -33.45,
            "LONGITUD_ESPERADA": -70.66,
            "RADIO_METROS": 150,
            "OPERATIVA": 1,
            "VERSION_ZP": "VTEST",
        }

    def registro(self, fecha, latitud=-33.45, longitud=-70.66):
        return SimpleNamespace(
            id=1,
            amid=7500001,
            fec_descarga=fecha,
            fec_estado=fecha,
            fecha_hora=fecha,
            fecha_registro=fecha,
            fecha_hora_anterior=None,
            transmitio_gps=True,
            latitud=latitud,
            longitud=longitud,
            porcentaje_bateria=75,
            is_contiene_gps=True,
            is_error_obtener_gps=False,
        )

    def parches_auxiliares(self, stack, vigente=None):
        stack.enter_context(patch(
            "apps.dashboard.services.gps_service.obtener_ahora_referencia",
            return_value=self.AHORA,
        ))
        stack.enter_context(patch(
            "apps.dashboard.services.gps_service.obtener_datos_ubicacion_amid_oracle",
            return_value=([], self.vigente if vigente is None else vigente),
        ))

    def test_fallback_usa_ultimo_dia_reportado_solo_en_rango_predeterminado(self):
        fecha_anterior = datetime(2026, 9, 8, 9, 0)
        request = self.factory.get("/gps/", {"amid": "7500001"})
        with ExitStack() as stack:
            self.parches_auxiliares(stack)
            mock_registros = stack.enter_context(patch(
                "apps.dashboard.services.gps_service.obtener_registros_gps_oracle",
                side_effect=[[], [self.registro(fecha_anterior)]],
            ))
            mock_ultimo = stack.enter_context(patch(
                "apps.dashboard.services.gps_service.obtener_ultimo_registro_gps_valido_oracle",
                return_value=self.registro(fecha_anterior),
            ))
            contexto = obtener_contexto_gps(request)

        mock_ultimo.assert_called_once_with("7500001")
        self.assertEqual(mock_registros.call_count, 2)
        self.assertTrue(contexto["usando_ultimo_dia_reportado"])
        self.assertEqual(contexto["fecha_ultimo_dia_reportado"], fecha_anterior.date())
        self.assertIn("08-09-2026", contexto["mensaje"])

    def test_gps_cero_hoy_no_activa_fallback(self):
        request = self.factory.get("/gps/", {"amid": "7500001"})
        with ExitStack() as stack:
            self.parches_auxiliares(stack)
            stack.enter_context(patch(
                "apps.dashboard.services.gps_service.obtener_registros_gps_oracle",
                return_value=[self.registro(datetime(2026, 9, 10, 9, 0), 0, 0)],
            ))
            mock_ultimo = stack.enter_context(patch(
                "apps.dashboard.services.gps_service.obtener_ultimo_registro_gps_valido_oracle"
            ))
            contexto = obtener_contexto_gps(request)

        mock_ultimo.assert_not_called()
        self.assertFalse(contexto["usando_ultimo_dia_reportado"])

    def test_rango_manual_sin_datos_no_activa_fallback(self):
        request = self.factory.get("/gps/", {
            "amid": "7500001",
            "rango_manual": "1",
            "fecha_desde": "2026-09-01",
            "fecha_hasta": "2026-09-02",
        })
        with ExitStack() as stack:
            self.parches_auxiliares(stack)
            stack.enter_context(patch(
                "apps.dashboard.services.gps_service.obtener_registros_gps_oracle",
                return_value=[],
            ))
            mock_ultimo = stack.enter_context(patch(
                "apps.dashboard.services.gps_service.obtener_ultimo_registro_gps_valido_oracle"
            ))
            contexto = obtener_contexto_gps(request)

        mock_ultimo.assert_not_called()
        self.assertFalse(contexto["usando_ultimo_dia_reportado"])

    def test_sin_coordenadas_retorna_mensaje_actual(self):
        request = self.factory.get("/gps/", {
            "amid": "7500001", "rango_manual": "1",
            "fecha_desde": "2026-09-10", "fecha_hasta": "2026-09-10",
        })
        with ExitStack() as stack:
            self.parches_auxiliares(stack)
            stack.enter_context(patch(
                "apps.dashboard.services.gps_service.obtener_registros_gps_oracle",
                return_value=[],
            ))
            contexto = obtener_contexto_gps(request)

        self.assertEqual(
            contexto["mensaje"],
            "No se encontraron coordenadas GPS para el AMID ingresado en el rango seleccionado.",
        )

    def test_error_oracle_retorna_mensaje_actual(self):
        request = self.factory.get("/gps/", {"amid": "7500001"})
        with ExitStack() as stack:
            self.parches_auxiliares(stack)
            stack.enter_context(patch(
                "apps.dashboard.services.gps_service.obtener_registros_gps_oracle",
                side_effect=RuntimeError("Oracle sintético no disponible"),
            ))
            stack.enter_context(patch(
                "apps.dashboard.services.gps_service.obtener_ultimo_registro_gps_valido_oracle"
            ))
            contexto = obtener_contexto_gps(request)

        self.assertEqual(
            contexto["mensaje"],
            "Error consultando datos GPS en Oracle: Oracle sintético no disponible",
        )

    def test_fallo_ubicacion_esperada_no_elimina_registros_gps(self):
        request = self.factory.get("/gps/", {"amid": "7500001"})
        registro = self.registro(datetime(2026, 9, 10, 9, 0))
        with patch(
            "apps.dashboard.services.gps_service.obtener_ahora_referencia",
            return_value=self.AHORA,
        ), patch(
            "apps.dashboard.services.gps_service.obtener_registros_gps_oracle",
            return_value=[registro],
        ), patch(
            "apps.dashboard.services.gps_service.obtener_datos_ubicacion_amid_oracle",
            side_effect=RuntimeError("ubicación sintética no disponible"),
        ):
            contexto = obtener_contexto_gps(request)

        self.assertEqual(len(contexto["historial_gps"]), 1)
        self.assertEqual(contexto["ultimo_registro"], registro)
        self.assertEqual(
            contexto["mensaje"],
            "Error consultando ubicación esperada en Oracle: ubicación sintética no disponible",
        )

    def test_fallo_horario_no_elimina_registros_gps(self):
        request = self.factory.get("/gps/", {"amid": "7500001"})
        registro = self.registro(datetime(2026, 9, 10, 9, 0))
        configuracion_inicial = crear_configuracion_horario_zp(
            fecha_referencia=self.AHORA
        )
        with ExitStack() as stack:
            self.parches_auxiliares(stack)
            stack.enter_context(patch(
                "apps.dashboard.services.gps_service.obtener_registros_gps_oracle",
                return_value=[registro],
            ))
            stack.enter_context(patch(
                "apps.dashboard.services.gps_service.crear_configuracion_horario_zp",
                side_effect=[
                    configuracion_inicial,
                    RuntimeError("horario sintético no disponible"),
                ],
            ))
            contexto = obtener_contexto_gps(request)

        self.assertEqual(len(contexto["historial_gps"]), 1)
        self.assertEqual(contexto["ultimo_registro"], registro)
        self.assertEqual(
            contexto["aviso_horario_zp"],
            "No fue posible consultar el horario vigente; los registros se mantienen sin filtro.",
        )
