"""
Pruebas de las tres vistas del módulo de Transacciones.

Se verifica el enrutado, la autorización y que las pantallas respondan sin
Oracle. No se comprueban cifras: eso requiere un dataset real y está fuera del
alcance de las pruebas unitarias.
"""

import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.transacciones.permisos import MENSAJE_SIN_PERMISO
from apps.transacciones.services import trx_service

RUTAS = (
    ("informe_interno", "/transacciones/informe-interno/"),
    ("mayor_15", "/transacciones/mayor-15/"),
    ("rezagadas", "/transacciones/rezagadas/"),
)

RAIZ = "/transacciones/"

CLOAVE = "clave-de-prueba-123"

# Nombres reales de `auth_group`. El gate lee `TRX_GRUPOS_PERMITIDOS`; estos
# literales comprueban de punta a punta que la configuración por defecto
# coincide con los grupos que existen en la base. `SONDA` va en mayúsculas:
# la comparación es case-sensitive y "Sonda" no es el mismo grupo.
GRUPO_ADMIN = "Admin"
GRUPO_SONDA = "SONDA"


def crear_usuario_plano(username):
    return get_user_model().objects.create_user(
        username=username,
        password=CLOAVE,
    )


def crear_sonda(username="sonda_test"):
    usuario = get_user_model().objects.create_user(
        username=username,
        password=CLOAVE,
    )
    grupo, _ = Group.objects.get_or_create(name=GRUPO_SONDA)
    usuario.groups.add(grupo)
    return usuario


def crear_admin_por_grupo(username="admin_grupo_test"):
    usuario = get_user_model().objects.create_user(
        username=username,
        password=CLOAVE,
    )
    grupo, _ = Group.objects.get_or_create(name=GRUPO_ADMIN)
    usuario.groups.add(grupo)
    return usuario


def crear_en_grupo(nombre_grupo, username):
    usuario = get_user_model().objects.create_user(
        username=username,
        password=CLOAVE,
    )
    grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
    usuario.groups.add(grupo)
    return usuario


def crear_superusuario(username="super_test"):
    return get_user_model().objects.create_superuser(
        username=username,
        email=f"{username}@example.test",
        password=CLOAVE,
    )


class UrlTests(TestCase):
    def test_las_tres_rutas_resuelven(self):
        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                self.assertEqual(reverse(f"transacciones:{nombre}"), ruta)


class AutorizacionTests(TestCase):
    """Sesión primero, permiso después.

    Un anónimo debe seguir viendo el 302 a login que el resto del dashboard
    ya tiene. El 403 es solo para quien tiene sesión pero no rol.
    """

    def setUp(self):
        self.usuario = crear_usuario_plano("transacciones")

    def test_las_tres_vistas_exigen_sesion(self):
        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)

                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta["Location"].startswith("/login/?next="))

    def test_la_raiz_tambien_exige_sesion(self):
        respuesta = self.client.get(RAIZ)

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith("/login/?next="))

    def test_usuario_sin_rol_recibe_403(self):
        self.client.force_login(self.usuario)

        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)

                self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(
                    respuesta.content.decode(),
                    MENSAJE_SIN_PERMISO,
                )

    def test_la_raiz_tambien_rechaza_sin_rol(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(RAIZ)

        self.assertEqual(respuesta.status_code, 403)

    def test_sonda_accede(self):
        self.client.force_login(crear_sonda())

        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)

                self.assertEqual(respuesta.status_code, 200)

    def test_admin_por_grupo_accede(self):
        self.client.force_login(crear_admin_por_grupo())

        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)

                self.assertEqual(respuesta.status_code, 200)

    def test_superusuario_accede(self):
        self.client.force_login(crear_superusuario())

        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)

                self.assertEqual(respuesta.status_code, 200)

    def test_un_grupo_distinto_no_da_acceso(self):
        """`Lab Dev` existe en `auth_group` pero no está en la política."""

        self.client.force_login(
            crear_en_grupo("Lab Dev", "otro_rol")
        )

        respuesta = self.client.get(reverse("transacciones:informe_interno"))

        self.assertEqual(respuesta.status_code, 403)

    @override_settings(TRX_GRUPOS_PERMITIDOS=("Consultoria Operativa",))
    def test_la_configuracion_llega_hasta_el_codigo_http(self):
        """Un grupo cualquiera entra si la configuración lo permite.

        Con la política escrita en el código este test da 403 y falla.
        """

        self.client.force_login(
            crear_en_grupo("Consultoria Operativa", "consultoria")
        )

        respuesta = self.client.get(reverse("transacciones:informe_interno"))

        self.assertEqual(respuesta.status_code, 200)

    def test_el_403_no_arma_contexto_ni_consulta(self):
        """El permiso se resuelve antes de la vista: nada de Oracle."""

        self.client.force_login(self.usuario)

        with mock.patch.object(trx_service, "obtener_dataset_base") as obtener:
            respuesta = self.client.get(reverse("transacciones:informe_interno"))

        self.assertEqual(respuesta.status_code, 403)
        obtener.assert_not_called()


class RedireccionRaizTests(TestCase):
    def setUp(self):
        self.client.force_login(crear_sonda("sonda_raiz"))

    def test_la_raiz_redirige_al_informe_interno(self):
        respuesta = self.client.get("/transacciones/")

        self.assertRedirects(
            respuesta,
            reverse("transacciones:informe_interno"),
            fetch_redirect_response=False,
        )


class RenderTests(TestCase):
    def setUp(self):
        self.client.force_login(crear_sonda("sonda_render"))

    def test_cada_pestana_usa_su_propio_template(self):
        esperados = {
            "informe_interno": "transacciones/informe_interno.html",
            "mayor_15": "transacciones/mayor_15.html",
            "rezagadas": "transacciones/rezagadas.html",
        }

        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)

                self.assertTemplateUsed(respuesta, esperados[nombre])
                self.assertTemplateUsed(
                    respuesta,
                    "transacciones/base_transacciones.html",
                )

    def test_sin_oracle_las_pantallas_muestran_el_aviso(self):
        respuesta = self.client.get(reverse("transacciones:informe_interno"))

        self.assertContains(respuesta, "Oracle deshabilitado")
        self.assertContains(respuesta, "placeholder", status_code=200)

    def test_no_se_inventan_datos_en_las_tablas(self):
        respuesta = self.client.get(reverse("transacciones:informe_interno"))

        self.assertContains(respuesta, "Sin datos en el rango seleccionado")
        self.assertNotContains(respuesta, "Informe_ZP_trxC2D_Interno.xlsx", html=False)


class RenderConDatosTests(TestCase):
    """
    Render con un dataset inyectado.

    Comprueba que una rezagada corta nunca se presente solo como "<= 5 min" en
    verde: su duracion es correcta, pero no describe su problema real.
    """

    def setUp(self):
        self.client.force_login(crear_sonda("sonda_datos"))

        rezagada = trx_service.normalizar_fila(
            {
                "nid_contexto_opte": "6",
                "num_abt": "000000123",
                "nid_contexto_switch": "0",
                "nid_terminal": "999",
                "amid": 7_500_003,
                "nid_sitio": "1234",
                "nombre_sitio": None,
                "nid_entidad_ot": "1",
                "nombre_entidad": "Operador Este",
                "cod_tipo_transaccion": "01",
                "n_modo": "4",
                "cod_proceso": "P1",
                "estado_envio": "E",
                "fec_trx": datetime.datetime(2026, 8, 26, 23, 59, 0),
                "fec_bd": datetime.datetime(2026, 8, 27, 0, 1, 0),
            }
        )

        self.comun = {
            "dataset": [rezagada],
            "total": 1,
            "consultado": True,
            "truncado": False,
            "mensaje": "",
        }

    def test_rezagada_corta_marca_su_estado(self):
        with mock.patch.object(
            trx_service, "obtener_dataset_base", return_value=self.comun
        ):
            respuesta = self.client.get(
                reverse("transacciones:rezagadas"),
                {"fecha": "2026-08-27"},
            )

        self.assertContains(respuesta, '<th scope="col">Estado</th>')
        self.assertContains(respuesta, "trx-pill trx-clase-rezagada")
        self.assertContains(respuesta, "Rezagada")
        self.assertContains(respuesta, "Sin sitio")

    def test_el_informe_interno_tambien_la_distingue(self):
        with mock.patch.object(
            trx_service, "obtener_dataset_base", return_value=self.comun
        ):
            respuesta = self.client.get(
                reverse("transacciones:informe_interno"),
                {"fecha": "2026-08-27"},
            )

        self.assertContains(respuesta, "trx-pill trx-clase-rezagada")

    def test_un_muestreo_acotado_se_avisa(self):
        comun = dict(self.comun, total=99_999, truncado=True)

        with mock.patch.object(
            trx_service, "obtener_dataset_base", return_value=comun
        ):
            respuesta = self.client.get(
                reverse("transacciones:rezagadas"),
                {"fecha": "2026-08-27"},
            )

        self.assertContains(respuesta, "muestra acotada")

    def test_las_pestanas_marcan_la_activa(self):
        respuesta = self.client.get(reverse("transacciones:rezagadas"))

        self.assertContains(respuesta, 'class="trx-pestana is-activa"', count=1)
        self.assertContains(respuesta, "Rezagadas")

    def test_los_filtros_conservan_la_querystring(self):
        respuesta = self.client.get(
            reverse("transacciones:mayor_15"),
            {"fecha_desde": "2026-08-27", "fecha_hasta": "2026-08-27"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "fecha_desde=2026-08-27")

    def test_rango_invalido_responde_igual_con_el_mensaje(self):
        respuesta = self.client.get(
            reverse("transacciones:informe_interno"),
            {"fecha_desde": "2026-01-01", "fecha_hasta": "2026-08-27"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "rango máximo")

    def test_filtros_que_bacan_del_oracle_no_rompen(self):
        for consulta in (
            {"fecha": "2026-08-27"},
            {"origen": "bd"},
            {"origen": "invalido"},
            {"amid": "7500001"},
            {"nidsitio": "1234"},
            {"nmodo": "4"},
            {"solo_mismo_dia": "1"},
        ):
            with self.subTest(consulta=consulta):
                respuesta = self.client.get(
                    reverse("transacciones:informe_interno"),
                    consulta,
                )

                self.assertEqual(respuesta.status_code, 200)


class SidebarTests(TestCase):
    """El enlace del módulo se oculta a quien no puede entrar.

    Ocultar el enlace es solo comodidad visual: la garantía real es el 403 de
    las vistas. Aquí se comprueba que el sidebar no invite a un 403.
    """

    def setUp(self):
        parche_carga = mock.patch(
            "apps.dashboard.context_processors.obtener_ultima_carga_datos_oracle",
            return_value=None,
        )
        parche_version = mock.patch(
            "apps.dashboard.context_processors.obtener_ultima_version_zp_oracle",
            return_value=None,
        )
        parche_carga.start()
        parche_version.start()
        self.addCleanup(parche_carga.stop)
        self.addCleanup(parche_version.stop)

        self.enlace = reverse("transacciones:informe_interno")

    def test_sonda_ve_el_enlace_una_sola_vez(self):
        self.client.force_login(crear_sonda("sonda_sidebar"))

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertContains(respuesta, self.enlace, count=1)

    def test_admin_por_grupo_ve_el_enlace(self):
        self.client.force_login(crear_admin_por_grupo("admin_sidebar"))

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertContains(respuesta, self.enlace, count=1)

    def test_superusuario_ve_el_enlace(self):
        self.client.force_login(crear_superusuario("super_sidebar"))

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertContains(respuesta, self.enlace, count=1)

    def test_usuario_sin_rol_no_ve_el_enlace(self):
        self.client.force_login(crear_usuario_plano("sin_rol_sidebar"))

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertNotContains(respuesta, self.enlace)

    def test_los_otros_enlaces_siguen_visibles_sin_rol(self):
        """Ocultar Transacciones no debe arrastrar al resto del menú."""

        self.client.force_login(crear_usuario_plano("sin_rol_menu"))

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertContains(respuesta, reverse("dashboard:panel_baterias"))
        self.assertContains(respuesta, reverse("dashboard:panel_alertas"))
        self.assertContains(respuesta, reverse("dashboard:panel_perfil"))
