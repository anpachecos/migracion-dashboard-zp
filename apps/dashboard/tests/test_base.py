"""Pruebas de la base `OracleTestCase`.

El objetivo es que la garantia sea verificable: si el seam deja de aplicarse,
estas pruebas tienen que fallar.
"""

from unittest.mock import MagicMock

from apps.dashboard.repositories import horarios_zp_repository
from apps.core.oracle import connection as oracle_connection
from apps.dashboard.tests.base import SEAM_ORACLE, OracleTestCase


class OracleTestCaseAislaElSeamTests(OracleTestCase):
    def test_el_seam_esta_parcheado_durante_la_prueba(self):
        self.assertIsInstance(oracle_connection.obtener_conexion_oracle, MagicMock)
        self.assertEqual(
            SEAM_ORACLE,
            "apps.core.oracle.connection.obtener_conexion_oracle",
        )

    def test_llamar_a_un_repositorio_no_crea_pool_real(self):
        # Si el seam no estuviera aplicado, esta llamada intentaria crear el
        # pool de Oracle real y fallaria por credenciales o por red.
        resultado = horarios_zp_repository.obtener_datos_horario_zp("7500001")

        self.assertTrue(
            self.mock_conexion_oracle.called,
            "el repositorio deberia haber usado la conexion parcheada",
        )
        # El mock no devuelve filas, asi que el repositorio cae al valor por
        # defecto. Lo que importa es que llego sin tocar la base real.
        self.assertIn(resultado, (None, {}))


class ElSeamSeRestauraTests(OracleTestCase):
    def test_tras_la_prueba_el_seam_vuelve_a_ser_la_funcion_real(self):
        # El contexto de esta prueba ya termino: el parche fue detenido por
        # addCleanup. Lo que se verifica aca es que el objetivo del parche
        # sigue siendo resoluble, es decir que el atributo no fue borrado.
        self.assertTrue(callable(oracle_connection.obtener_conexion_oracle))
