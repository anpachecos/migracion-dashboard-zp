"""Base de pruebas con el seam de Oracle garantizado.

Las pruebas que llegan a un repositorio deben heredar de `OracleTestCase`. El
parche se aplica en `setUp`, de modo que ningun test pueda abrir por olvido una
conexion real a Oracle.

Desde `cfeb893` los nueve repositorios acceden por modulo, asi que un unico
parche cubre a todos. Antes habia que repetir la ruta completa
`apps.<app>.repositories.<repo>.obtener_conexion_oracle` en cada prueba, y
olvidarse una sola vez significaba conectarse a la base de produccion.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

SEAM_ORACLE = "apps.core.oracle.connection.obtener_conexion_oracle"


class OracleTestCase(SimpleTestCase):
    """Intercepte `obtener_conexion_oracle` durante la prueba."""

    mock_conexion_oracle = None

    def setUp(self):
        super().setUp()
        parche = patch(SEAM_ORACLE)
        self.mock_conexion_oracle = parche.start()
        self.addCleanup(parche.stop)
