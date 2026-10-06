"""
Pruebas de la vista del Monitor de Traspaso C2D.

El modulo es una sola pagina con cuatro pestanas de estado de cliente, asi que
la vista solo arma el armazon: no consulta la base y las cifras las pide el
`dataService` del navegador. Estas pruebas fijan lo que no debe romperse al
seguir disenando: el enrutado, el permiso, el enlace del sidebar, que el
armazon y las cuatro secciones esten, y que el umbral de corte llegue desde
`trx_reglas` en vez de estar escrito en el template.

Las rutas que existian por pestana (`informe-interno`, `mayor-15`, `rezagadas`)
se conservaron como redirecciones para no romper los enlaces ya compartidos.

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

# La pagina que renderiza.
RUTAS = (
    ("monitor", "/transacciones/monitor/"),
)

# Las rutas por pestana que quedaron como redireccion, con la pestana del
# monitor a la que debe llevar cada una.
RUTAS_LEGADAS = (
    ("informe_interno", "/transacciones/informe-interno/", 0),
    ("mayor_15", "/transacciones/mayor-15/", 2),
    ("rezagadas", "/transacciones/rezagadas/", 3),
)

RAIZ = "/transacciones/"

CLOAVE = "clave-de-prueba-123"

# Nombres reales de `auth_group`. El gate lee `TRX_GRUPOS_PERMITIDOS`; estos
# literales comprueban de punta a punta que la configuracion por defecto
# coincide con los grupos que existen en la base. `SONDA` va en mayusculas:
# la comparacion es case-sensitive y "Sonda" no es el mismo grupo.
GRUPO_ADMIN = "Admin"
GRUPO_SONDA = "SONDA"

# El h1 vive en el armazon y no depende del contexto: si cambia, hay que
# actualizar la prueba a proposito, no por descuido.
H1 = "Monitor de Traspaso C2D"

# Las cuatro pestanas, en el orden en que aparecen.
PESTANAS = ("Resumen mensual", "Resumen diario", "Dispositivos", "Rezagadas")

# Monitor y rutas legadas: todas pasan por el mismo permiso.
TODAS_LAS_RUTAS = RUTAS + tuple((nombre, ruta) for nombre, ruta, _ in RUTAS_LEGADAS)


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
    def test_las_rutas_resuelven(self):
        for nombre, ruta in RUTAS:
            with self.subTest(pestana=nombre):
                self.assertEqual(reverse(f"transacciones:{nombre}"), ruta)

    def test_las_rutas_legadas_siguen_existiendo(self):
        """Los enlaces ya compartidos no se rompen, ahora redirigen."""

        for nombre, ruta, _ in RUTAS_LEGADAS:
            with self.subTest(ruta=nombre):
                self.assertEqual(reverse(f"transacciones:{nombre}"), ruta)


class AutorizacionTests(TestCase):
    """Sesion primero, permiso despues.

    Un anonimo debe seguir viendo el 302 a login que el resto del dashboard
    ya tiene. El 403 es solo para quien tiene sesion pero no rol.
    """

    def setUp(self):
        self.usuario = crear_usuario_plano("transacciones")

    def test_todas_las_vistas_exigen_sesion(self):
        for nombre, ruta in TODAS_LAS_RUTAS:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)

                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta["Location"].startswith("/login/?next="))

    def test_la_raiz_tambien_exige_sesion(self):
        respuesta = self.client.get(RAIZ)

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith("/login/?next="))

    def test_usuario_sin_rol_recibe_403(self):
        self.client.force_login(self.usuario)

        for nombre, ruta in TODAS_LAS_RUTAS:
            with self.subTest(ruta=ruta):
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

        respuesta = self.client.get(reverse("transacciones:monitor"))

        self.assertEqual(respuesta.status_code, 403)

    @override_settings(TRX_GRUPOS_PERMITIDOS=("Consultoria Operativa",))
    def test_la_configuracion_llega_hasta_el_codigo_http(self):
        """Un grupo cualquiera entra si la configuracion lo permite.

        Con la politica escrita en el codigo este test da 403 y falla.
        """

        self.client.force_login(
            crear_en_grupo("Consultoria Operativa", "consultoria")
        )

        respuesta = self.client.get(reverse("transacciones:monitor"))

        self.assertEqual(respuesta.status_code, 200)

    def test_el_403_no_arma_contexto_ni_consulta(self):
        """El permiso se resuelve antes de la vista: nada de Oracle."""

        self.client.force_login(self.usuario)

        with mock.patch.object(trx_service, "obtener_dataset_base") as obtener:
            respuesta = self.client.get(reverse("transacciones:monitor"))

        self.assertEqual(respuesta.status_code, 403)
        obtener.assert_not_called()


class RedireccionRaizTests(TestCase):
    def setUp(self):
        self.client.force_login(crear_sonda("sonda_raiz"))

    def test_la_raiz_redirige_al_monitor(self):
        respuesta = self.client.get("/transacciones/")

        self.assertRedirects(
            respuesta,
            reverse("transacciones:monitor"),
            fetch_redirect_response=False,
        )

    def test_cada_ruta_legada_lleva_a_su_pestana(self):
        """Enlace guardado a una pestana: abre esa pestana, no la primera."""

        for nombre, ruta, numero in RUTAS_LEGADAS:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)

                self.assertEqual(respuesta.status_code, 302)
                self.assertEqual(
                    respuesta["Location"],
                    reverse("transacciones:monitor") + f"?p={numero}",
                )

    def test_el_monitor_es_la_pestana_por_defecto(self):
        """Sin query string arranca en el resumen mensual.

        El HTML del servidor solo trae la primera marcada: mover la marca es
        cosa del script, que la corre a partir del `p` de la URL.
        """

        html = self.client.get(
            reverse("transacciones:monitor")
        ).content.decode()

        self.assertNotIn("?p=", html)
        self.assertEqual(html.count('aria-selected="true"'), 1)
        self.assertRegex(
            html,
            r'data-trx-tab="0" aria-selected="true"',
        )


class RenderTests(TestCase):
    """El armazon del monitor renderiza con las cuatro secciones.

    Lo que se fija es la estructura: que use su template, que el encabezado y
    las cuatro pestanas esten, que la seccion de cada pestana exista aunque el
    JS no haya corrido todavia, y que el umbral llegue desde el contexto.
    """

    def setUp(self):
        self.client.force_login(crear_sonda("sonda_render"))

    def test_usa_su_template_y_el_compartido(self):
        respuesta = self.client.get(reverse("transacciones:monitor"))

        self.assertTemplateUsed(respuesta, "transacciones/monitor.html")
        self.assertTemplateUsed(
            respuesta,
            "transacciones/base_transacciones.html",
        )
        self.assertTemplateUsed(respuesta, "dashboard/base_dashboard.html")

    def test_muestra_el_encabezado(self):
        respuesta = self.client.get(reverse("transacciones:monitor"))

        self.assertContains(respuesta, H1, status_code=200)
        self.assertContains(respuesta, "<h1>", status_code=200)

    def test_las_cuatro_pestanas_estan_en_el_menu(self):
        """El menu es boton, no enlace: la navegacion ya no cambia de URL.

        El filtro global vive en el shell, asi que esta es la unica navegacion
        que sobrevive: si se cae, el monitor queda en una sola pestana.
        """

        html = self.client.get(reverse("transacciones:monitor")).content.decode()

        for numero, etiqueta in enumerate(PESTANAS):
            with self.subTest(pestana=etiqueta):
                self.assertIn(f'data-trx-tab="{numero}"', html)
                self.assertIn(f">{etiqueta}<", html)

    def test_solo_una_pestana_queda_seleccionada(self):
        """El nav marca la primera por defecto; el JS mueve la marca."""

        html = self.client.get(reverse("transacciones:monitor")).content.decode()

        self.assertEqual(html.count('aria-selected="true"'), 1)
        self.assertEqual(html.count('aria-selected="false"'), 3)

    def test_cada_pestana_tiene_su_seccion(self):
        """Las cuatro secciones existen en el HTML aunque el JS no corra.

        Es lo que evita el salto de layout: la seccion se pinta vacia y el JS la
        llena. Si alguien borra una seccion del template, esta prueba lo dice.
        """

        html = self.client.get(reverse("transacciones:monitor")).content.decode()

        for numero in range(4):
            with self.subTest(pestana=numero):
                self.assertIn(f'id="trx-seccion-{numero}"', html)
                self.assertIn(f'data-trx-seccion="{numero}"', html)

    def test_las_secciones_distintas_de_la_primera_nacen_escondidas(self):
        """Solo la mensual se muestra sin esperar al script.

        Con `hidden` en las otras tres no hay nada que parpadee mientras carga.
        """

        html = self.client.get(reverse("transacciones:monitor")).content.decode()

        for numero in (1, 2, 3):
            with self.subTest(pestana=numero):
                self.assertRegex(
                    html,
                    rf'data-trx-seccion="{numero}"[^>]*\shidden',
                )

    def test_los_filtros_globales_existen(self):
        html = self.client.get(reverse("transacciones:monitor")).content.decode()

        for nombre in ("mes", "operador", "tipo"):
            with self.subTest(filtro=nombre):
                self.assertIn(f'data-trx-globales="{nombre}"', html)

        self.assertIn("data-trx-limpiar-globales", html)

    def test_los_filtros_de_la_lista_solo_en_la_pestana_de_dispositivos(self):
        """Buscador y chips son de esa pestana, no del armazon."""

        html = self.client.get(reverse("transacciones:monitor")).content.decode()

        seccion = html.split('id="trx-seccion-2"')[1].split("</section>")[0]

        self.assertIn("data-trx-buscar", seccion)
        for chip in ("all", "bad", "crit", "rec", "lab"):
            with self.subTest(chip=chip):
                self.assertIn(f'data-trx-chip="{chip}"', seccion)

    def test_el_umbral_llega_desde_el_contexto(self):
        """El umbral se inyecta, no esta escrito en el HTML.

        Se compara contra `trx_reglas` para que cambiarlo en la fuente no rompa
        la prueba.
        """

        html = self.client.get(reverse("transacciones:monitor")).content.decode()

        self.assertIn(
            'data-umbral-corte-min="{}"'.format(
                trx_reglas.UMBRAL_CORTE_MINUTOS
            ),
            html,
        )

    def test_carga_los_assets_del_modulo(self):
        """El orden importa: `mockData` antes que `dataService` y `app`."""

        html = self.client.get(reverse("transacciones:monitor")).content.decode()

        for activo in (
            "transacciones/css/monitor_traspaso.css",
            "transacciones/js/config.js",
            "transacciones/js/mockData.js",
            "transacciones/js/utils.js",
            "transacciones/js/charts.js",
            "transacciones/js/dataService.js",
            "transacciones/js/app.js",
        ):
            with self.subTest(activo=activo):
                self.assertIn(activo, html)

        orden = [
            html.index("js/" + nombre)
            for nombre in (
                "config.js",
                "mockData.js",
                "utils.js",
                "charts.js",
                "dataService.js",
                "app.js",
            )
        ]

        self.assertEqual(orden, sorted(orden))

    def test_los_assets_salen_por_estatico(self):
        """El modulo no debe abrir el arbol de archivos por su cuenta."""

        html = self.client.get(reverse("transacciones:monitor")).content.decode()

        self.assertNotIn("apps/transacciones/static", html)
        self.assertNotIn("file://", html)

    def test_ningun_comentario_de_template_llega_al_html(self):
        """Django solo borra `{# #}` de una linea.

        Un `{# #}` repartido en varias lineas no lo agarra el tokenizador y sale
        al HTML tal cual, se lee como texto de la pagina. Para bloques va
        `{% comment %}`, que si es multilinea. Esta prueba fija la diferencia.
        """

        html = self.client.get(reverse("transacciones:monitor")).content.decode()

        self.assertNotIn("{#", html)
        self.assertNotIn("#}", html)
        self.assertNotIn("{% comment", html)
        self.assertNotIn("{% endcomment", html)

    def test_no_deja_markup_del_esqueleto_anterior(self):
        """Las zonas de la version anterior no deben quedar colgando."""

        html = self.client.get(reverse("transacciones:monitor")).content.decode()

        self.assertNotIn("partials/", html)
        self.assertNotIn("trx-placeholder", html)


class RenderSinOracleTests(TestCase):
    """Con Oracle apagado el monitor igual renderiza.

    La vista no consulta la base, asi que un fallo de conexion no puede tirar
    la pagina: los datos salen de `mockData.js` en el navegador.
    """

    def setUp(self):
        self.client.force_login(crear_sonda("sonda_sin_oracle"))

    def test_el_monitor_responde_sin_oracle(self):
        with mock.patch.object(
            trx_service,
            "obtener_dataset_base",
            side_effect=AssertionError("la vista no debe consultar"),
        ):
            respuesta = self.client.get(reverse("transacciones:monitor"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, H1)


class FiltrosTests(TestCase):
    """La querystring no puede romper el armazon.

    El JS valida `p`, `fecha` y `mes` al leer la URL, pero el servidor tiene que
    responder 200 igual: una URL vieja con parametros raros no debe ser un 500.
    """

    def setUp(self):
        self.client.force_login(crear_sonda("sonda_filtros"))

    def test_rango_invalido_responde_igual(self):
        respuesta = self.client.get(
            reverse("transacciones:monitor"),
            {"fecha_desde": "2026-01-01", "fecha_hasta": "2026-08-27"},
        )

        self.assertEqual(respuesta.status_code, 200)

    def test_filtros_que_bacan_del_oracle_no_rompen(self):
        for consulta in (
            {"fecha": "2026-08-27"},
            {"mes": "2026-08"},
            {"mes": "basura"},
            {"p": "9"},
            {"p": "-1"},
            {"p": "abc"},
            {"origen": "bd"},
            {"origen": "invalido"},
            {"amid": "7500001"},
            {"nidsitio": "1234"},
            {"nmodo": "4"},
            {"solo_mismo_dia": "1"},
        ):
            with self.subTest(consulta=consulta):
                respuesta = self.client.get(
                    reverse("transacciones:monitor"),
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

        self.enlace = reverse("transacciones:monitor")

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

        self.enlace = reverse("transacciones:monitor")

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
    """El armazon no muestra cifras, y no debe empezar a hacerlo solo.

    El monitor dibuja con `mockData.js` en el navegador. Si un dia se enchufa la
    base, tiene que ser por el `dataService` y no colando una consulta en la
    vista: estos datos jamas deben aparecer en el HTML del servidor.
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

    def test_el_monitor_no_saca_cifras_de_la_base(self):
        with mock.patch.object(
            trx_service, "obtener_dataset_base", return_value=self.comun
        ):
            respuesta = self.client.get(
                reverse("transacciones:monitor"),
                {"fecha": "2026-08-27"},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, H1)
        self.assertNotContains(respuesta, "000000123")
        self.assertNotContains(respuesta, "7.500.003")
        self.assertNotContains(respuesta, "Operador Este")
