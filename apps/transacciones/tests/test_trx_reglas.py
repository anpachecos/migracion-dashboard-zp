"""
Pruebas del punto central de reglas de `apps.transacciones`.

Este archivo protege las reglas funcionales validadas contra regresiones. Si
alguien cambia un umbral o una condición de borde, estas pruebas fallan antes
de que el cambio llegue a Oracle o a un Excel.
"""

from datetime import datetime

from django.test import SimpleTestCase

from apps.transacciones.services import trx_reglas


class ClasificacionTests(SimpleTestCase):
    def test_cinco_minutos_exactos_queda_en_hasta_5(self):
        self.assertEqual(
            trx_reglas.clasificar(300),
            trx_reglas.CLASIFICACION_HASTA_5,
        )

    def test_cinco_minutos_un_segundo_sale_de_hasta_5(self):
        self.assertEqual(
            trx_reglas.clasificar(301),
            trx_reglas.CLASIFICACION_5_A_15,
        )

    def test_quince_minutos_exactos_no_es_mayor_a_15(self):
        self.assertEqual(
            trx_reglas.clasificar(900),
            trx_reglas.CLASIFICACION_5_A_15,
        )

    def test_quince_minutos_un_segundo_si_es_mayor_a_15(self):
        self.assertEqual(
            trx_reglas.clasificar(901),
            trx_reglas.CLASIFICACION_MAYOR_15,
        )

    def test_sin_dato_no_se_clasifica(self):
        self.assertEqual(
            trx_reglas.clasificar(None),
            trx_reglas.CLASIFICACION_SIN_DATO,
        )

    def test_duracion_negativa_no_se_clasifica(self):
        self.assertEqual(
            trx_reglas.clasificar(-1),
            trx_reglas.CLASIFICACION_SIN_DATO,
        )


class TramosTests(SimpleTestCase):
    def test_limites_de_tramos_son_inclusivos_y_contiguos(self):
        for clave, etiqueta, minimo, maximo, rango, orden in trx_reglas.TRAMOS:
            with self.subTest(tramo=clave):
                self.assertEqual(
                    trx_reglas.obtener_tramo(minimo)["clave"],
                    clave,
                    f"El mínimo de {clave} debe caer dentro del propio tramo.",
                )

                if maximo is not None:
                    self.assertEqual(
                        trx_reglas.obtener_tramo(maximo)["clave"],
                        clave,
                        f"El máximo de {clave} debe caer dentro del propio tramo.",
                    )

    def test_tramos_no_dejan_huecos(self):
        for anterior, siguiente in zip(trx_reglas.TRAMOS, trx_reglas.TRAMOS[1:]):
            with self.subTest(entre=f"{anterior[0]}-{siguiente[0]}"):
                self.assertEqual(
                    anterior[3] + 1,
                    siguiente[2],
                    "El tramo siguiente debe arrancar un segundo después.",
                )

    def test_orden_de_tramos_es_creciente(self):
        ordenes = [tramo[5] for tramo in trx_reglas.TRAMOS]
        self.assertEqual(ordenes, sorted(ordenes))

    def test_duracion_sin_dato_no_tiene_tramo(self):
        self.assertIsNone(trx_reglas.obtener_tramo(None))

    def test_duracion_mayor_al_ultimo_tramo_cae_en_mas_2(self):
        self.assertEqual(
            trx_reglas.obtener_tramo(86_400)["clave"],
            "mas_2",
        )


class FormateoDuracionTests(SimpleTestCase):
    def test_formatea_con_ceros_a_la_izquierda(self):
        self.assertEqual(trx_reglas.formatear_duracion(0), "00:00:00")
        self.assertEqual(trx_reglas.formatear_duracion(5), "00:00:05")
        self.assertEqual(trx_reglas.formatear_duracion(301), "00:05:01")
        self.assertEqual(trx_reglas.formatear_duracion(3661), "01:01:01")
        self.assertEqual(trx_reglas.formatear_duracion(86_400), "24:00:00")

    def test_sin_dato_texto_explicito(self):
        self.assertEqual(trx_reglas.formatear_duracion(None), "Sin dato")
        self.assertEqual(trx_reglas.formatear_duracion(-5), "Sin dato")


class MismoDiaYRezagoTests(SimpleTestCase):
    def test_mismo_dia_calendario(self):
        trx = datetime(2026, 8, 27, 10, 0, 0)
        bd = datetime(2026, 8, 27, 23, 59, 59)

        self.assertTrue(trx_reglas.es_mismo_dia(trx, bd))
        self.assertFalse(trx_reglas.es_rezagada(trx, bd))
        self.assertEqual(trx_reglas.calcular_dias_rezago(trx, bd), 0)

    def test_cambio_de_dia_con_un_minuto_de_diferencia_es_rezagada(self):
        trx = datetime(2026, 8, 27, 23, 59, 0)
        bd = datetime(2026, 8, 28, 0, 0, 0)

        self.assertFalse(trx_reglas.es_mismo_dia(trx, bd))
        self.assertTrue(trx_reglas.es_rezagada(trx, bd))
        self.assertEqual(trx_reglas.calcular_dias_rezago(trx, bd), 1)

    def test_cambio_de_dia_nunca_es_mayor_15_mismo_dia(self):
        trx = datetime(2026, 8, 27, 1, 0, 0)
        bd = datetime(2026, 8, 30, 4, 0, 0)
        segundos = int((bd - trx).total_seconds())

        self.assertEqual(trx_reglas.calcular_dias_rezago(trx, bd), 3)
        self.assertGreater(segundos, trx_reglas.UMBRAL_CORTE_SEGUNDOS)
        self.assertFalse(trx_reglas.es_mayor_15_mismo_dia(trx, bd, segundos))

    def test_rezago_no_tiene_techo_de_dias(self):
        trx = datetime(2026, 8, 1, 10, 0, 0)
        bd = datetime(2026, 9, 1, 10, 0, 0)

        self.assertEqual(trx_reglas.calcular_dias_rezago(trx, bd), 31)

    def test_fechas_ausentes_no_producen_rezago(self):
        self.assertFalse(trx_reglas.es_mismo_dia(None, None))
        self.assertFalse(trx_reglas.es_rezagada(None, None))
        self.assertEqual(trx_reglas.calcular_dias_rezago(None, None), 0)


class MayorQuinceMinTests(SimpleTestCase):
    def test_requiere_mismo_dia_y_superar_quince_minutos(self):
        trx = datetime(2026, 8, 27, 10, 0, 0)
        bd = datetime(2026, 8, 27, 10, 15, 0)

        self.assertFalse(
            trx_reglas.es_mayor_15_mismo_dia(trx, bd, 15 * 60)
        )
        self.assertTrue(
            trx_reglas.es_mayor_15_mismo_dia(trx, bd, 15 * 60 + 1)
        )

    def test_rezagada_larga_no_entra_a_mayor_15(self):
        trx = datetime(2026, 8, 26, 10, 0, 0)
        bd = datetime(2026, 8, 27, 12, 0, 0)

        self.assertFalse(
            trx_reglas.es_mayor_15_mismo_dia(trx, bd, 26 * 3_600)
        )

    def test_sin_duracion_no_entra_a_mayor_15(self):
        trx = datetime(2026, 8, 27, 10, 0, 0)
        bd = datetime(2026, 8, 27, 10, 0, 0)

        self.assertFalse(trx_reglas.es_mayor_15_mismo_dia(trx, bd, None))
