from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.dashboard.services.baterias_service import (
    construir_datos_grafico_dia,
    construir_datos_grafico_periodo,
    construir_tabla_bateria,
    obtener_clase_bateria,
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
