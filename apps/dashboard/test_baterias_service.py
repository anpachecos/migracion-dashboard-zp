from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.dashboard.services.baterias_service import (
    construir_datos_grafico_dia,
    construir_datos_grafico_periodo,
    construir_tabla_bateria,
    obtener_clase_bateria,
    obtener_contexto_baterias,
    obtener_ultimo_registro_bateria_oracle,
)


class BateriasServiceLogicaPuraTests(SimpleTestCase):
    AHORA = datetime(2026, 9, 10, 12, 0)

    def bloque(self, hora, bateria, tiene_dato=True):
        return SimpleNamespace(
            fecha_hora_bloque=hora,
            hora_bloque=hora.strftime("%H:%M"),
            porcentaje_bateria=bateria,
            tiene_dato=tiene_dato,
        )

    def construir_tabla(self, bloques=None, cantidad_dias=14):
        with patch(
            "apps.dashboard.services.baterias_service.obtener_ahora_referencia",
            return_value=self.AHORA,
        ):
            return construir_tabla_bateria(
                bloques=bloques or [],
                cantidad_dias=cantidad_dias,
            )

    def test_bateria_cero_se_conserva_como_dato_real(self):
        bloque = self.bloque(datetime(2026, 9, 10, 8, 0), 0)

        columnas, tabla = self.construir_tabla([bloque], cantidad_dias=1)

        indice = columnas.index("08:00")
        self.assertEqual(tabla[0]["valores"][indice]["valor"], 0)

    def test_bloque_sin_dato_queda_vacio(self):
        bloque = self.bloque(
            datetime(2026, 9, 10, 8, 0),
            65,
            tiene_dato=False,
        )

        columnas, tabla = self.construir_tabla([bloque], cantidad_dias=1)

        indice = columnas.index("08:00")
        self.assertEqual(tabla[0]["valores"][indice]["valor"], "")

    def test_tabla_bateria_genera_catorce_dias_desde_hoy_hacia_atras(self):
        columnas, tabla = self.construir_tabla()

        self.assertEqual(len(columnas), 48)
        self.assertEqual(len(tabla), 14)
        self.assertEqual(tabla[0]["fecha"], "10-09-2026")
        self.assertEqual(tabla[-1]["fecha"], "28-08-2026")

    def test_grafico_dia_ordena_bloques_cronologicamente(self):
        bloques = [
            self.bloque(datetime(2026, 9, 10, 10, 0), 70),
            self.bloque(datetime(2026, 9, 10, 9, 0), 76),
        ]

        datos = construir_datos_grafico_dia(
            bloques,
            fecha_objetivo=self.AHORA.date(),
        )

        self.assertEqual(datos[0]["hora"], "09:00")
        self.assertEqual(datos[-1]["hora"], "10:00")
        self.assertEqual(datos[0]["bateria_real"], 76.0)
        self.assertEqual(datos[-1]["bateria_real"], 70.0)

    def test_curva_esperada_comienza_en_primer_valor_mayor_que_cero(self):
        bloques = [
            self.bloque(datetime(2026, 9, 10, 8, 0), 0),
            self.bloque(datetime(2026, 9, 10, 8, 30), 50),
        ]

        datos = construir_datos_grafico_dia(
            bloques,
            fecha_objetivo=self.AHORA.date(),
        )

        self.assertEqual(datos[0]["bateria_real"], 0.0)
        self.assertIsNone(datos[0]["bateria_esperada"])
        self.assertEqual(datos[1]["bateria_esperada"], 50.0)

    def test_curva_esperada_desciende_tres_puntos_por_bloque(self):
        bloques = [
            self.bloque(datetime(2026, 9, 10, 8, 0), 60),
            self.bloque(datetime(2026, 9, 10, 9, 0), 54),
        ]

        datos = construir_datos_grafico_dia(
            bloques,
            fecha_objetivo=self.AHORA.date(),
        )

        self.assertEqual(
            [punto["bateria_esperada"] for punto in datos],
            [60.0, 57.0, 54.0],
        )

    def test_grafico_dia_sin_datos_reales_retorna_lista_vacia(self):
        bloques = [
            self.bloque(
                datetime(2026, 9, 10, 8, 0),
                None,
                tiene_dato=False,
            )
        ]

        datos = construir_datos_grafico_dia(
            bloques,
            fecha_objetivo=self.AHORA.date(),
        )

        self.assertEqual(datos, [])

    def test_grafico_periodo_queda_en_orden_cronologico(self):
        _, tabla = self.construir_tabla(
            [
                self.bloque(datetime(2026, 9, 9, 8, 0), 80),
                self.bloque(datetime(2026, 9, 10, 8, 0), 77),
            ],
            cantidad_dias=2,
        )

        datos = construir_datos_grafico_periodo(tabla)

        self.assertEqual(datos[0]["momento"], "09-09-2026 00:00")
        self.assertEqual(datos[-1]["momento"], "10-09-2026 23:30")
        self.assertLess(
            next(i for i, punto in enumerate(datos) if punto["bateria_real"] == 80),
            next(i for i, punto in enumerate(datos) if punto["bateria_real"] == 77),
        )

    def test_bloque_duplicado_conserva_el_ultimo_procesado(self):
        hora = datetime(2026, 9, 10, 8, 0)
        columnas, tabla = self.construir_tabla(
            [self.bloque(hora, 80), self.bloque(hora, 70)],
            cantidad_dias=1,
        )

        indice = columnas.index("08:00")
        self.assertEqual(tabla[0]["valores"][indice]["valor"], 70)

    def test_bateria_cero_recibe_clasificacion_critica_actual(self):
        self.assertEqual(obtener_clase_bateria(0), "bateria-critica")


class BateriasServiceContextoTests(SimpleTestCase):
    AHORA = datetime(2026, 9, 10, 12, 0)

    def setUp(self):
        self.factory = RequestFactory()

    def ultimo_registro(self, fecha=None):
        fecha = fecha or datetime(2026, 9, 10, 9, 0)
        return SimpleNamespace(
            id=1,
            amid=7500001,
            fec_descarga=fecha,
            fec_estado=fecha,
            fecha_hora=fecha,
            busid="BUS-SINTETICO",
            op="OP-SINTETICA",
            version="VTEST",
            patente="TEST01",
            td01=None,
            td04=None,
            porcentaje_bateria=76,
            is_contiene_bateria=True,
            is_error_obtener_bateria=False,
        )

    def resumen_alerta(self):
        return SimpleNamespace(
            nivel_alerta_bateria="ALERTA",
            total_caidas=2,
            caidas_hoy=1,
            caidas_hist=1,
            ultima_fecha_caida=datetime(2026, 9, 10, 8, 30),
            ultima_caida_desde=80,
            ultima_caida_hasta=60,
            ultima_caida_dif=-20,
            motivo_alerta_bateria="Caídas sintéticas",
        )

    def ejecutar_contexto(self, ultimo=None, resumen=None):
        request = self.factory.get("/baterias/", {"amid": "7500001"})
        with patch(
            "apps.dashboard.services.baterias_service.obtener_ahora_referencia",
            return_value=self.AHORA,
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_bloques_bateria_oracle",
            return_value=[],
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_ultimo_registro_bateria_oracle",
            return_value=ultimo,
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_resumen_alerta_bateria_oracle",
            return_value=resumen,
        ):
            return obtener_contexto_baterias(request)

    def test_contexto_siempre_consulta_catorce_dias_completos(self):
        request = self.factory.get("/baterias/", {"amid": "7500001"})
        with patch(
            "apps.dashboard.services.baterias_service.obtener_ahora_referencia",
            return_value=self.AHORA,
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_bloques_bateria_oracle",
            return_value=[],
        ) as mock_bloques, patch(
            "apps.dashboard.services.baterias_service.obtener_ultimo_registro_bateria_oracle",
            return_value=None,
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_resumen_alerta_bateria_oracle",
            return_value=None,
        ):
            contexto = obtener_contexto_baterias(request)

        self.assertEqual(contexto["dias"], 14)
        self.assertEqual(contexto["hora_inicio"], "00:00")
        self.assertEqual(contexto["hora_fin"], "23:30")
        mock_bloques.assert_called_once_with(
            amid="7500001",
            fecha_inicio=datetime(2026, 8, 28, 0, 0),
            fecha_fin=datetime(2026, 9, 11, 0, 0),
        )

    def test_amid_invalido_retorna_mensaje_actual(self):
        request = self.factory.get("/baterias/", {"amid": "invalido"})
        with patch(
            "apps.dashboard.services.baterias_service.obtener_bloques_bateria_oracle",
            side_effect=ValueError,
        ):
            contexto = obtener_contexto_baterias(request)

        self.assertEqual(contexto["mensaje"], "El AMID ingresado no es válido.")

    def test_amid_sin_registros_retorna_mensaje_actual(self):
        contexto = self.ejecutar_contexto(ultimo=None, resumen=None)

        self.assertEqual(
            contexto["mensaje"],
            "No se encontraron registros para el AMID ingresado.",
        )

    def test_fallo_detalle_caidas_conserva_resumen_oracle(self):
        resumen = self.resumen_alerta()
        request = self.factory.get("/baterias/", {"amid": "7500001"})
        with patch(
            "apps.dashboard.services.baterias_service.obtener_ahora_referencia",
            return_value=self.AHORA,
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_bloques_bateria_oracle",
            return_value=[],
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_ultimo_registro_bateria_oracle",
            return_value=self.ultimo_registro(),
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_resumen_alerta_bateria_oracle",
            return_value=resumen,
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_datos_horario_zp_oracle",
            return_value=None,
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_detalle_caidas_bateria_oracle",
            side_effect=RuntimeError("detalle sintético no disponible"),
        ):
            contexto = obtener_contexto_baterias(request)

        self.assertIs(contexto["resumen_alerta_bateria"], resumen)
        self.assertEqual(contexto["total_caidas_drasticas"], 2)
        self.assertFalse(contexto["detalle_alertas_completo"])
        self.assertTrue(contexto["alertas_periodo"])

    @patch("apps.dashboard.services.baterias_service.obtener_conexion_oracle")
    def test_ultimo_registro_selecciona_el_mas_reciente(self, mock_conexion):
        cursor = mock_conexion.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        fecha = datetime(2026, 9, 10, 11, 30)
        cursor.fetchone.return_value = (
            2, 7500001, fecha, fecha, "BUS", "OP", "VTEST", "TEST01",
            None, None, fecha, 71, 1, 0,
        )
        cursor.description = [(nombre,) for nombre in (
            "ID", "AMID", "FEC_DESCARGA", "FEC_ESTADO", "BUSID", "OP",
            "VERSION", "PATENTE", "TD01", "TD04", "FECHA_HORA",
            "PORCENTAJE_BATERIA", "IS_CONTIENE_BATERIA",
            "IS_ERROR_OBTENER_BATERIA",
        )]

        registro = obtener_ultimo_registro_bateria_oracle("7500001")

        consulta = cursor.execute.call_args.args[0]
        self.assertIn("ORDER BY FECHA_HORA DESC", consulta)
        self.assertIn("WHERE ROWNUM = 1", consulta)
        self.assertEqual(registro.id, 2)
        self.assertEqual(registro.fecha_hora, fecha)

    def test_fallo_horario_no_impide_mostrar_bateria(self):
        request = self.factory.get("/baterias/", {"amid": "7500001"})
        ultimo = self.ultimo_registro()
        with patch(
            "apps.dashboard.services.baterias_service.obtener_ahora_referencia",
            return_value=self.AHORA,
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_bloques_bateria_oracle",
            return_value=[],
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_ultimo_registro_bateria_oracle",
            return_value=ultimo,
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_resumen_alerta_bateria_oracle",
            return_value=None,
        ), patch(
            "apps.dashboard.services.baterias_service.obtener_datos_horario_zp_oracle",
            side_effect=RuntimeError("horario sintético no disponible"),
        ):
            contexto = obtener_contexto_baterias(request)

        self.assertIs(contexto["ultimo_registro"], ultimo)
        self.assertEqual(contexto["ultimo_registro"].porcentaje_bateria, 76)
        self.assertEqual(contexto["clase_bateria_actual"], "tarjeta-warning")
        self.assertEqual(
            contexto["aviso_horario_zp"],
            "No fue posible consultar el horario vigente; la tabla se mantiene completa.",
        )

    def test_error_oracle_se_transforma_en_mensaje_actual(self):
        request = self.factory.get("/baterias/", {"amid": "7500001"})
        with patch(
            "apps.dashboard.services.baterias_service.obtener_bloques_bateria_oracle",
            side_effect=RuntimeError("Oracle sintético no disponible"),
        ):
            contexto = obtener_contexto_baterias(request)

        self.assertEqual(
            contexto["mensaje"],
            "Error consultando datos de baterías en Oracle: Oracle sintético no disponible",
        )
