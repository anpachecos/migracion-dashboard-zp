"""
Pruebas del gate de acceso a Transacciones.

La política de acceso vive en `TRX_GRUPOS_PERMITIDOS`, así que el gate se
prueba sobre esa configuración y no sobre constantes del código. El caso
central es `test_cualquier_grupo_configurado_da_acceso`: con la política
escrita en el código fallaría, que es exactamente la propiedad que se quiere
garantizar.

El parseo de la variable de entorno se prueba en un subproceso porque ocurre
al importar `config.settings`, siguiendo el patrón de
`apps/dashboard/test_settings_fail_closed.py`. Los grupos reales en base de
datos se cubren en `test_transacciones_views.py`.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, override_settings

from apps.transacciones.permisos import usuario_puede_ver_transacciones

GRUPO_ADMIN = "Admin"
GRUPO_SONDA = "SONDA"


class GruposSimulados:
    """Doble de `user.groups` que registra el filtro aplicado."""

    def __init__(self, nombres_pertenecientes):
        self.nombres = set(nombres_pertenecientes)
        self.filtros = []

    def filter(self, name__in=None, **kwargs):
        self.filtros.append(name__in)
        return SimpleNamespace(exists=lambda: bool(self.nombres & set(name__in)))


def usuario(is_authenticated=True, is_superuser=False, grupos=()):
    return SimpleNamespace(
        is_authenticated=is_authenticated,
        is_superuser=is_superuser,
        groups=GruposSimulados(grupos),
    )


class PoliticaConfiguradaTests(SimpleTestCase):
    def test_el_anonimo_no_pasa(self):
        self.assertFalse(
            usuario_puede_ver_transacciones(AnonymousUser())
        )

    def test_el_superusuario_pasa_sin_consultar_grupos(self):
        """El superusuario entra siempre, con lista vacía o no."""

        candidato = usuario(is_superuser=True, grupos=[])

        with override_settings(TRX_GRUPOS_PERMITIDOS=()):
            self.assertTrue(usuario_puede_ver_transacciones(candidato))

        self.assertEqual(candidato.groups.filtros, [])

    @override_settings(TRX_GRUPOS_PERMITIDOS=(GRUPO_ADMIN, GRUPO_SONDA))
    def test_el_grupo_sonda_configurado_pasa(self):
        self.assertTrue(
            usuario_puede_ver_transacciones(usuario(grupos=[GRUPO_SONDA]))
        )

    @override_settings(TRX_GRUPOS_PERMITIDOS=(GRUPO_ADMIN, GRUPO_SONDA))
    def test_el_grupo_admin_configurado_pasa(self):
        self.assertTrue(
            usuario_puede_ver_transacciones(usuario(grupos=[GRUPO_ADMIN]))
        )

    @override_settings(TRX_GRUPOS_PERMITIDOS=(GRUPO_ADMIN, GRUPO_SONDA))
    def test_sin_grupos_no_pasa(self):
        self.assertFalse(usuario_puede_ver_transacciones(usuario(grupos=[])))

    @override_settings(TRX_GRUPOS_PERMITIDOS=(GRUPO_ADMIN, GRUPO_SONDA))
    def test_un_grupo_ajeno_no_pasa(self):
        self.assertFalse(
            usuario_puede_ver_transacciones(usuario(grupos=["Lab Dev"]))
        )

    @override_settings(TRX_GRUPOS_PERMITIDOS=(GRUPO_ADMIN, GRUPO_SONDA))
    def test_los_nombres_de_grupo_son_case_sensitive(self):
        """`Sonda` y `admin` no son `SONDA` ni `Admin`."""

        self.assertFalse(
            usuario_puede_ver_transacciones(usuario(grupos=["sonda"]))
        )
        self.assertFalse(
            usuario_puede_ver_transacciones(usuario(grupos=["admin"]))
        )
        self.assertFalse(
            usuario_puede_ver_transacciones(usuario(grupos=["Sonda"]))
        )

    @override_settings(TRX_GRUPOS_PERMITIDOS=("Consultoria Operativa",))
    def test_cualquier_grupo_configurado_da_acceso(self):
        """La política es configuración, no una constante en el código.

        Con los nombres de grupo escritos en el código este test falla.
        """

        self.assertTrue(
            usuario_puede_ver_transacciones(
                usuario(grupos=["Consultoria Operativa"])
            )
        )

    @override_settings(TRX_GRUPOS_PERMITIDOS=("Consultoria Operativa",))
    def test_un_grupo_que_ya_no_esta_configurado_no_pasa(self):
        """Quitar un grupo de la configuración le quita el acceso."""

        self.assertFalse(
            usuario_puede_ver_transacciones(usuario(grupos=[GRUPO_SONDA]))
        )

    @override_settings(TRX_GRUPOS_PERMITIDOS=())
    def test_lista_vacia_deja_solo_superusuarios(self):
        """Fail-closed: una lista vacía no abre nada por accidente."""

        candidato = usuario(grupos=[GRUPO_ADMIN, GRUPO_SONDA])

        self.assertFalse(usuario_puede_ver_transacciones(candidato))
        self.assertEqual(candidato.groups.filtros, [])

    @override_settings(TRX_GRUPOS_PERMITIDOS=(GRUPO_ADMIN, GRUPO_SONDA))
    def test_todos_los_grupos_se_consultan_en_una_sola_pregunta(self):
        """Una query, no dos: es el camino caliente de cada request."""

        candidato = usuario(grupos=[GRUPO_SONDA])

        usuario_puede_ver_transacciones(candidato)

        self.assertEqual(
            candidato.groups.filtros,
            [(GRUPO_ADMIN, GRUPO_SONDA)],
        )


class ParseoVariableEntornoTests(SimpleTestCase):
    """La tupla se construye al importar settings, así que va en subproceso."""

    RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
    SECRET_KEY = "clave-sintetica-exclusiva-para-tests-1234567890"
    AUSENTE = object()

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
    "grupos": list(project_settings.TRX_GRUPOS_PERMITIDOS),
}))
"""

    def cargar_grupos(self, valor):
        entorno = os.environ.copy()
        entorno.pop("TRX_GRUPOS_PERMITIDOS", None)
        entorno["SECRET_KEY"] = self.SECRET_KEY

        if valor is not self.AUSENTE:
            entorno["TRX_GRUPOS_PERMITIDOS"] = valor

        proceso = subprocess.run(
            [sys.executable, "-c", self.SCRIPT_CARGA_SETTINGS],
            cwd=self.RAIZ_PROYECTO,
            env=entorno,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        salida = proceso.stdout.strip().splitlines()
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        return json.loads(salida[-1])["grupos"]

    def test_default_es_admin_y_sonda(self):
        self.assertEqual(
            self.cargar_grupos(self.AUSENTE),
            ["Admin", "SONDA"],
        )

    def test_lista_simple(self):
        self.assertEqual(
            self.cargar_grupos("Admin,SONDA"),
            ["Admin", "SONDA"],
        )

    def test_tolera_espacios_around(self):
        self.assertEqual(
            self.cargar_grupos("  Admin , SONDA  "),
            ["Admin", "SONDA"],
        )

    def test_tolera_espacios_entre_guiones(self):
        """CADENAS.txt a veces traen separadores con espacios."""

        self.assertEqual(
            self.cargar_grupos("Admin, SONDA , Lab Dev"),
            ["Admin", "SONDA", "Lab Dev"],
        )

    def test_descarta_elementos_vacios(self):
        self.assertEqual(
            self.cargar_grupos("Admin,,SONDA,"),
            ["Admin", "SONDA"],
        )

    def test_valor_vacio_produce_lista_vacia(self):
        self.assertEqual(self.cargar_grupos(""), [])

    def test_valor_con_solo_espacios_produce_lista_vacia(self):
        self.assertEqual(self.cargar_grupos("   "), [])

    def test_preserva_las_mayusculas_del_nombre(self):
        """`SONDA` en minúsculas rompería el acceso: no se normaliza."""

        self.assertEqual(
            self.cargar_grupos("Sonda"),
            ["Sonda"],
        )
