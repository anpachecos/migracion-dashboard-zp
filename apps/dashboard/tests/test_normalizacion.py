"""Pruebas de `normalizacion` y `claves_cache`.

El contrato de `normalizar_booleano_oracle` es de tres valores: True, False o
None. None significa "sin dato" y lo usan los paneles para mostrar el estado
neutro, por eso ningun valor desconocido colapsa a False.
"""

from django.test import SimpleTestCase

from apps.dashboard.services import claves_cache
from apps.dashboard.services.normalizacion import (
    convertir_numero,
    normalizar_booleano_oracle,
    normalizar_fecha_para_comparar,
    obtener_ahora_referencia,
)


class ObtenerAhoraReferenciaTests(SimpleTestCase):
    def test_devuelve_un_datetime_naive(self):
        ahora = obtener_ahora_referencia()

        from datetime import datetime

        self.assertIsInstance(ahora, datetime)
        self.assertFalse(getattr(ahora, "tzinfo", None))


class NormalizarFechaParaCompararTests(SimpleTestCase):
    def test_valor_vacio_devuelve_none(self):
        self.assertIsNone(normalizar_fecha_para_comparar(None))
        self.assertIsNone(normalizar_fecha_para_comparar(""))

    def test_conserva_fechas_naive(self):
        from datetime import datetime

        fecha = datetime(2026, 9, 10, 12, 30)

        self.assertEqual(normalizar_fecha_para_comparar(fecha), fecha)


class NormalizarBooleanoOracleTests(SimpleTestCase):
    def test_valores_verdaderos(self):
        for valor in [True, 1, "true", "TRUE", "1", "si", "sí", "s", "yes", "y"]:
            with self.subTest(valor=valor):
                self.assertIs(normalizar_booleano_oracle(valor), True)

    def test_valores_falsos(self):
        for valor in [False, 0, "false", "FALSE", "0", "no", "n"]:
            with self.subTest(valor=valor):
                self.assertIs(normalizar_booleano_oracle(valor), False)

    def test_none_significa_sin_dato(self):
        self.assertIsNone(normalizar_booleano_oracle(None))

    def test_valor_no_reconocido_devuelve_none_no_false(self):
        # Ningun valor desconocido se colapsa a False: se pierde el "sin dato".
        self.assertIsNone(normalizar_booleano_oracle("quizas"))
        self.assertIsNone(normalizar_booleano_oracle(""))
        self.assertIsNone(normalizar_booleano_oracle(2))

    def test_numeros_distintos_de_u_no_son_uno(self):
        self.assertEqual(normalizar_booleano_oracle(1.0), True)
        self.assertEqual(normalizar_booleano_oracle(0.0), False)

    def test_objeto_con_str_en_lista_se_normaliza(self):
        self.assertIs(normalizar_booleano_oracle("  SI  "), True)


class ConvertirNumeroTests(SimpleTestCase):
    def test_valores_validos_a_float(self):
        self.assertEqual(convertir_numero("12.5"), 12.5)
        self.assertEqual(convertir_numero(8), 8.0)

    def test_valores_invalidos_devuelven_none(self):
        self.assertIsNone(convertir_numero(None))
        self.assertIsNone(convertir_numero(""))
        self.assertIsNone(convertir_numero("abc"))


class ClavesCacheTests(SimpleTestCase):
    def test_resumen_de_alertas_es_una_sola_clave_compartida(self):
        # reglas_alertas_service.borrar y alertas_service.leer/escribir deben
        # usar la misma clave o la invalidacion de cache se pierde.
        self.assertEqual(claves_cache.CACHE_KEY_RESUMEN_ALERTAS, "dashboard:resumen-alertas-activos:v3")

    def test_todas_las_claves_estan_definidas(self):
        self.assertTrue(claves_cache.CACHE_KEY_RESUMEN_ALERTAS)
        self.assertTrue(claves_cache.CACHE_KEY_UBICACIONES_ALERTAS)
        self.assertTrue(claves_cache.CACHE_KEY_ULTIMA_CARGA_DATOS)
        self.assertTrue(claves_cache.CACHE_KEY_ULTIMA_VERSION_ZP)

    def test_los_servicios_importan_la_misma_constante(self):
        from apps.dashboard.services.alertas_service import CACHE_KEY_RESUMEN_ALERTAS as alertas
        from apps.dashboard.services.reglas_alertas_service import CACHE_KEY_RESUMEN_ALERTAS as reglas

        self.assertEqual(alertas, reglas)
        self.assertEqual(reglas, "dashboard:resumen-alertas-activos:v3")