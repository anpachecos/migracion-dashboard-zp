import json
import os
from pathlib import Path
import subprocess
import sys

from django.test import SimpleTestCase


class SettingsFailClosedTests(SimpleTestCase):
    RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
    SECRET_KEY_SINTETICA = "clave-sintetica-exclusiva-para-tests-1234567890"
    SCRIPT_CARGA_SETTINGS = r"""
import json
import sys
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured

try:
    with patch("dotenv.load_dotenv", return_value=False):
        import config.settings as project_settings
except ImproperlyConfigured as error:
    print(json.dumps({"error": str(error)}))
    sys.exit(2)

print(json.dumps({
    "secret_configurada": bool(project_settings.SECRET_KEY),
    "debug": project_settings.DEBUG,
    "allowed_hosts": project_settings.ALLOWED_HOSTS,
}))
"""

    AUSENTE = object()

    def cargar_settings(
        self,
        secret_key=SECRET_KEY_SINTETICA,
        debug=AUSENTE,
        allowed_hosts=AUSENTE,
    ):
        entorno = os.environ.copy()

        for variable in ("SECRET_KEY", "DEBUG", "ALLOWED_HOSTS"):
            entorno.pop(variable, None)

        if secret_key is not self.AUSENTE:
            entorno["SECRET_KEY"] = secret_key
        if debug is not self.AUSENTE:
            entorno["DEBUG"] = debug
        if allowed_hosts is not self.AUSENTE:
            entorno["ALLOWED_HOSTS"] = allowed_hosts

        proceso = subprocess.run(
            [sys.executable, "-c", self.SCRIPT_CARGA_SETTINGS],
            cwd=self.RAIZ_PROYECTO,
            env=entorno,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        salida = proceso.stdout.strip().splitlines()
        datos = json.loads(salida[-1]) if salida else {}
        return proceso, datos

    def afirmar_error_secret_key(self, valor):
        proceso, datos = self.cargar_settings(secret_key=valor)
        self.assertEqual(proceso.returncode, 2, proceso.stderr)
        self.assertEqual(
            datos["error"],
            "SECRET_KEY debe estar definida en las variables de entorno.",
        )
        return proceso, datos

    def afirmar_debug(self, valor, esperado):
        proceso, datos = self.cargar_settings(debug=valor)
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        self.assertIs(datos["debug"], esperado)

    def test_secret_key_presente_permite_cargar_settings(self):
        proceso, datos = self.cargar_settings()
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        self.assertTrue(datos["secret_configurada"])

    def test_secret_key_ausente_falla_de_forma_controlada(self):
        self.afirmar_error_secret_key(self.AUSENTE)

    def test_secret_key_vacia_falla_de_forma_controlada(self):
        self.afirmar_error_secret_key("")

    def test_secret_key_con_solo_espacios_falla_de_forma_controlada(self):
        self.afirmar_error_secret_key("   ")

    def test_error_secret_key_no_expone_el_valor(self):
        proceso, datos = self.afirmar_error_secret_key(" \t ")
        salida = proceso.stdout + proceso.stderr
        self.assertEqual(
            set(datos),
            {"error"},
        )
        self.assertNotIn("SECRET_KEY=", salida)

    def test_debug_ausente_es_false(self):
        self.afirmar_debug(self.AUSENTE, False)

    def test_debug_true_con_mayuscula_es_true(self):
        self.afirmar_debug("True", True)

    def test_debug_true_minusculo_es_true(self):
        self.afirmar_debug("true", True)

    def test_debug_true_mayusculo_es_true(self):
        self.afirmar_debug("TRUE", True)

    def test_debug_uno_es_true(self):
        self.afirmar_debug("1", True)

    def test_debug_yes_es_true(self):
        self.afirmar_debug("yes", True)

    def test_debug_on_es_true(self):
        self.afirmar_debug("on", True)

    def test_debug_false_con_mayuscula_es_false(self):
        self.afirmar_debug("False", False)

    def test_debug_false_minusculo_es_false(self):
        self.afirmar_debug("false", False)

    def test_debug_cero_es_false(self):
        self.afirmar_debug("0", False)

    def test_debug_no_es_false(self):
        self.afirmar_debug("no", False)

    def test_debug_off_es_false(self):
        self.afirmar_debug("off", False)

    def test_debug_tolera_espacios_externos(self):
        self.afirmar_debug("  YeS  ", True)

    def test_debug_invalido_falla_explicita_y_seguramente(self):
        proceso, datos = self.cargar_settings(debug="maybe")
        self.assertEqual(proceso.returncode, 2, proceso.stderr)
        self.assertEqual(
            datos["error"],
            "DEBUG debe usar uno de estos valores: "
            "true, 1, yes, on, false, 0, no u off.",
        )
        self.assertNotIn("maybe", datos["error"])

    def test_allowed_hosts_ausente_conserva_default_restrictivo(self):
        proceso, datos = self.cargar_settings(allowed_hosts=self.AUSENTE)
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        self.assertEqual(datos["allowed_hosts"], ["localhost", "127.0.0.1"])
