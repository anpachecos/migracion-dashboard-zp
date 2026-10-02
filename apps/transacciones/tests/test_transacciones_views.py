"""
Pruebas de las tres vistas del modulo de Transacciones.

Este modulo esta en un esqueleto: las tres rutas existen, se autorizan y
renderizan, pero el contenido visual se va a construir desde cero. Las pruebas
cubren la estructura que no debe romperse al disenar el mockup (enrutado,
permisos, sidebar y la presencia de los titulos) y deliberadamente no comprueban
cifras ni markup, que todavia no existe.

Las pruebas de la capa de datos viven en `test_trx_service`, `test_trx_reglas`,
`test_trx_repository` e `test_informes_trx`.
"""

import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.transacciones.permisos import MENSAJE_SIN_PERMISO
from apps.transacciones.services import trx_reglas, trx_service

RUTAS = (
    ("informe_interno", "/transacciones/informe-interno/"),
    ("mayor_15", "/transacciones/mayor-15/"),
    ("rezagadas", "/transacciones/rezagadas/"),
)

RAIZ = "/transacciones/"

CLOAVE = "clave-de-prueba-123"

# Nombres reales de `auth_group`. El gate lee `TRX_GRUPOS_PERMITIDOS`; estos
# literales comprueban de punta a punta que la configuracion por defecto
# coincide con los grupos que existen en la base. `SONDA` va en mayusculas:
# la comparacion es case-sensitive y "Sonda" no es el mismo grupo.
GRUPO_ADMIN = "Admin"
GRUPO_SONDA = "SONDA"

# El h1 vive en el esqueleto y no depende del contexto: si cambia, hay que
# actualizar la prueba a proposito, no por descuido.
H1 = "Monitor de Traspaso C2D"


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
    """Sesion primero, permiso despues.

    Un anonimo debe seguir viendo el 302 a login que el resto del dashboard
    ya tiene. El 403 es solo para quien tiene sesion pero no rol.
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
        """`Lab Dev` existe en `auth_group` pero no esta en la politica."""

        self.client.force_login(
            crear_en_grupo("Lab Dev", "otro_rol")
        )

        respuesta = self.client.get(reverse("transacciones:informe_interno"))

        self.assertEqual(respuesta.status_code, 403)

    @override_settings(TRX_GRUPOS_PERMITIDOS=("Consultoria Operativa",))
    def test_la_configuracion_llega_hasta_el_codigo_http(self):
        """Un grupo cualquiera entra si la configuracion lo permite.

        Con la politica escrita en el codigo este test da 403 y falla.
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
    """El esqueleto renderiza en las tres pestanas.

    Lo unico que se fija es la estructura: que cada ruta use su template, que el
    encabezado y las tres pestanas esten, y que la pestana activa se marque.
    """

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

    def test_las_tres_pantallas_muestran_el_encabezado(self):
        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)

                self.assertContains(respuesta, H1, status_code=200)
                self.assertContains(respuesta, "<h1>", status_code=200)

    def test_las_tres_pestanas_estan_en_el_menu(self):
        """Las tres rutas tienen que quedar enlazadas desde cualquier pestana.

        El menu vive en el esqueleto, asi que es la unica navegacion que
        sobrevive al vaciado: si se cae, las tres rutas quedan huerfanas.
        """

        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)

                for otro, ruta_otro in RUTAS:
                    self.assertContains(
                        respuesta,
                        f'href="{ruta_otro}"',
                    )

    def test_cada_pestana_muestra_su_propio_titulo(self):
        """El titulo de cada pestana sale del contexto, no de un literal.

        Se importan las etiquetas de `trx_service` y `trx_reglas` en vez de
        escribirlas aca, para que cambiar el umbral de corte no rompa la prueba.
        """

        esperados = {
            "informe_interno": trx_service.ETIQUETAS_PESTANA["informe_interno"],
            "mayor_15": trx_reglas.ETIQUETA_ESTADO_UMBRAL,
            "rezagadas": trx_service.ETIQUETAS_PESTANA["rezagadas"],
        }

        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)

                self.assertContains(
                    respuesta,
                    f"<h2>{esperados[nombre]}</h2>",
                    status_code=200,
                )

    def test_solo_una_pestana_queda_marcada_como_activa(self):
        """El nav marca una sola pestaña activa: la de la ruta visitada.

        Se comprueba `is-activa` y no `aria-current="page"`, porque el enlace del
        sidebar tambi\u00e9n lleva `aria-current` en las tres rutas y contarlo global
        dar\u00eda dos.
        """

        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                html = self.client.get(ruta).content.decode()

                self.assertEqual(html.count('data-trx-pestana="'), 3)
                self.assertEqual(html.count("is-activa"), 1)
                self.assertRegex(
                    html,
                    rf'data-trx-pestana="{nombre}"\s+class="is-activa"',
                )

    def test_las_pestanas_inactivas_no_cargan_la_marca(self):
        for nombre, ruta in RUTAS:
            for otro, _ in RUTAS:
                if otro == nombre:
                    continue

                with self.subTest(visita=nombre, inactiva=otro):
                    html = self.client.get(ruta).content.decode()

                    self.assertRegex(
                        html,
                        rf'data-trx-pestana="{otro}"\s+class=""',
                    )

    def test_el_esqueleto_no_carga_assets_de_transacciones(self):
        """Ni CSS ni JS propios: el modulo se arma desde cero.

        Fija el punto de partida. Cuando se agreguen, esta prueba hay que
        borrarla a proposito.
        """

        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)
                html = respuesta.content.decode()

                self.assertNotIn("transacciones.css", html)
                self.assertNotIn("transacciones/js/", html)
                self.assertNotIn("mock.js", html)

    def test_el_esqueleto_no_conserva_markup_legacy(self):
        """Las zonas de la version anterior no deben quedar colgando.

        Si alguien reAgrega un include de `partials/` o un bloque `trx_*` viejo
        sin querer, esta prueba lo delata.
        """

        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)
                html = respuesta.content.decode()

                self.assertNotIn("partials/", html)
                self.assertNotIn("trx-placeholder", html)
                self.assertNotIn("trx-kpis", html)
                self.assertNotIn("trx-tabla", html)


class RenderSinOracleTests(TestCase):
    """Con Oracle apagado las tres pantallas igual renderizan.

    El esqueleto no muestra cifras, pero el contexto igual pasa por los services:
    que fallen al consultar no puede tumbar la pagina.
    """

    def setUp(self):
        self.client.force_login(crear_sonda("sonda_sin_oracle"))

    def test_las_tres_pantallas_responden_sin_oracle(self):
        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                respuesta = self.client.get(ruta)

                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, H1)


class FiltrosTests(TestCase):
    """Los services siguen validando la querystring aunque nadie la muestre.

    El esqueleto todavia no dibuja filtros, pero el gate de los services no
    puede romperse: un rango invalido tiene que seguir respondiendo 200.
    """

    def setUp(self):
        self.client.force_login(crear_sonda("sonda_filtros"))

    def test_rango_invalido_responde_igual(self):
        respuesta = self.client.get(
            reverse("transacciones:informe_interno"),
            {"fecha_desde": "2026-01-01", "fecha_hasta": "2026-08-27"},
        )

        self.assertEqual(respuesta.status_code, 200)

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
    """El enlace del modulo se oculta a quien no puede entrar.

    Ocultar el enlace es solo comodidad visual: la garantia real es el 403 de
    las vistas. Aqui se comprueba que el sidebar no invite a un 403.
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
        """Ocultar Transacciones no debe arrastrar al resto del menu."""

        self.client.force_login(crear_usuario_plano("sin_rol_menu"))

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertContains(respuesta, reverse("dashboard:panel_baterias"))
        self.assertContains(respuesta, reverse("dashboard:panel_alertas"))
        self.assertContains(respuesta, reverse("dashboard:panel_perfil"))


class SidebarGrupoReportesTests(TestCase):
    """El grupo Reportes se oculta entero, no solo el enlace.

    El sidebar agrupa la navegacion en `<details>`. Si el `{% if %}` envolviera
    solo el enlace, quien no puede entrar veria el rotulo "Reportes" con un
    grupo vacio, que es peor que no ver nada.
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

    def test_autorizado_ve_el_grupo_completo(self):
        self.client.force_login(crear_sonda("sonda_grupo"))

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertContains(respuesta, "Reportes", count=1)
        self.assertContains(respuesta, self.enlace, count=1)

    def test_sin_acceso_no_ve_el_rotulo_del_grupo(self):
        """El rotulo es la parte que se olvida al condicionar."""

        self.client.force_login(crear_usuario_plano("sin_grupo"))

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertNotContains(respuesta, "Reportes")
        self.assertNotContains(respuesta, self.enlace)

    def test_sin_acceso_los_otros_grupos_siguen_intactos(self):
        self.client.force_login(crear_usuario_plano("sin_grupo_resto"))

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertContains(respuesta, "Operación")
        self.assertContains(respuesta, "Administración")


class DatosNoInventadosTests(TestCase):
    """El esqueleto no muestra cifras, y no debe empezar a hacerlo solo.

    Con el dataset inyectado la pagina tiene que seguir igual de vacia: ningun
    numero de la base puede aparecer sin que el diseno lo pida.
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

    def test_el_esqueleto_no_saca_cifras_de_la_base(self):
        with mock.patch.object(
            trx_service, "obtener_dataset_base", return_value=self.comun
        ):
            respuesta = self.client.get(
                reverse("transacciones:rezagadas"),
                {"fecha": "2026-08-27"},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, H1)
        self.assertNotContains(respuesta, "000000123")
        self.assertNotContains(respuesta, "7.500.003")
        self.assertNotContains(respuesta, "Operador Este")
