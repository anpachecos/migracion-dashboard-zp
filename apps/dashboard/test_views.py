from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook


class DashboardViewsCaracterizacionTests(TestCase):
    AHORA = datetime(2026, 9, 11, 12, 34, 56)

    @classmethod
    def setUpTestData(cls):
        usuarios = get_user_model()
        cls.usuario = usuarios.objects.create_user(
            username="usuario_test",
            password="clave-test",
        )
        cls.admin = usuarios.objects.create_superuser(
            username="admin_test",
            email="admin@example.test",
            password="clave-test",
        )

    def setUp(self):
        parche_carga = patch(
            "apps.dashboard.context_processors.obtener_ultima_carga_datos_oracle",
            return_value=None,
        )
        parche_version = patch(
            "apps.dashboard.context_processors.obtener_ultima_version_zp_oracle",
            return_value=None,
        )
        parche_carga.start()
        parche_version.start()
        self.addCleanup(parche_carga.stop)
        self.addCleanup(parche_version.stop)

    def autenticar(self, admin=False):
        self.client.force_login(self.admin if admin else self.usuario)

    def mensajes(self, response):
        return [str(mensaje) for mensaje in get_messages(response.wsgi_request)]

    def test_usuario_anonimo_es_redirigido_a_login_en_views_principales(self):
        for nombre in (
            "dashboard:panel_baterias",
            "dashboard:panel_gps",
            "dashboard:panel_alertas",
            "dashboard:panel_perfil",
        ):
            with self.subTest(view=nombre):
                url = reverse(nombre)
                response = self.client.get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('login')}?next={url}",
                    fetch_redirect_response=False,
                )

    def test_panel_baterias_usa_template_contexto_y_get_actual(self):
        self.autenticar()
        contexto_servicio = {
            "amid": "7500001",
            "mensaje": "",
            "tabla_bateria": [{"fecha": "11-09-2026"}],
        }
        with patch(
            "apps.dashboard.views.obtener_contexto_baterias",
            return_value=contexto_servicio,
        ) as mock_servicio:
            response = self.client.get(
                reverse("dashboard:panel_baterias"),
                {"amid": "7500001", "horario_zp": "1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/panel_baterias.html")
        self.assertEqual(response.context["active_page"], "baterias")
        self.assertEqual(response.context["amid"], "7500001")
        self.assertEqual(response.context["tabla_bateria"], contexto_servicio["tabla_bateria"])
        request = mock_servicio.call_args.args[0]
        self.assertEqual(request.GET["amid"], "7500001")
        self.assertEqual(request.GET["horario_zp"], "1")

    def test_panel_baterias_muestra_mensaje_actual_del_servicio(self):
        self.autenticar()
        with patch(
            "apps.dashboard.views.obtener_contexto_baterias",
            return_value={
                "amid": "invalido",
                "mensaje": "El AMID ingresado no es válido.",
            },
        ):
            response = self.client.get(
                reverse("dashboard:panel_baterias"), {"amid": "invalido"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["mensaje"], "El AMID ingresado no es válido.")

    def test_panel_gps_usa_template_contexto_y_get_actual(self):
        self.autenticar()
        contexto_servicio = {
            "amid": "7500001",
            "mensaje": "",
            "ubicaciones_gps": [{"latitud": -33.45, "longitud": -70.66}],
            "horario_zp": {
                "ubicacion": "Zona sintética",
                "tiene_horario_hoy": False,
                "texto_hoy": "Sin horario",
                "items": [],
                "mensaje_hoy": "Sin horario asignado hoy",
            },
        }
        with patch(
            "apps.dashboard.views.obtener_contexto_gps",
            return_value=contexto_servicio,
        ) as mock_servicio:
            response = self.client.get(
                reverse("dashboard:panel_gps"),
                {
                    "amid": "7500001",
                    "rango_manual": "1",
                    "fecha_desde": "2026-09-10",
                    "fecha_hasta": "2026-09-11",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/panel_gps.html")
        self.assertEqual(response.context["active_page"], "gps")
        self.assertEqual(response.context["ubicaciones_gps"], contexto_servicio["ubicaciones_gps"])
        request = mock_servicio.call_args.args[0]
        self.assertEqual(request.GET["amid"], "7500001")
        self.assertEqual(request.GET["rango_manual"], "1")

    def test_panel_gps_muestra_mensaje_sin_datos_del_servicio(self):
        self.autenticar()
        mensaje = "No se encontraron coordenadas GPS para el AMID ingresado en el rango seleccionado."
        with patch(
            "apps.dashboard.views.obtener_contexto_gps",
            return_value={
                "amid": "7500001",
                "mensaje": mensaje,
                "ubicaciones_gps": [],
                "horario_zp": {
                    "ubicacion": "Zona sintética",
                    "tiene_horario_hoy": False,
                    "texto_hoy": "Sin horario",
                    "items": [],
                    "mensaje_hoy": "Sin horario asignado hoy",
                },
            },
        ):
            response = self.client.get(
                reverse("dashboard:panel_gps"), {"amid": "7500001"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["mensaje"], mensaje)
        self.assertEqual(response.context["ubicaciones_gps"], [])

    def test_paneles_retornan_500_si_el_servicio_propaga_una_excepcion(self):
        self.autenticar()
        self.client.raise_request_exception = False
        casos = (
            ("dashboard:panel_baterias", "apps.dashboard.views.obtener_contexto_baterias"),
            ("dashboard:panel_gps", "apps.dashboard.views.obtener_contexto_gps"),
        )
        for nombre, dependencia in casos:
            with self.subTest(view=nombre), patch(
                dependencia,
                side_effect=RuntimeError("fallo sintético del servicio"),
            ):
                response = self.client.get(reverse(nombre), {"amid": "7500001"})
                self.assertEqual(response.status_code, 500)

    def test_logout_post_redirige_al_login_y_cierra_sesion(self):
        self.autenticar()
        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_exportaciones_estandar_sin_amid_retornan_400(self):
        self.autenticar()
        for nombre in (
            "dashboard:exportar_baterias_excel",
            "dashboard:exportar_gps_excel",
        ):
            with self.subTest(view=nombre):
                response = self.client.get(reverse(nombre))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.content.decode(), "Debe indicar un AMID para exportar.")

    def test_exportaciones_estandar_con_amid_invalido_retornan_400(self):
        self.autenticar()
        for nombre in (
            "dashboard:exportar_baterias_excel",
            "dashboard:exportar_gps_excel",
        ):
            with self.subTest(view=nombre), patch(
                "apps.dashboard.views.crear_excel_completo_amid",
                side_effect=ValueError,
            ):
                response = self.client.get(reverse(nombre), {"amid": "invalido"})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.content.decode(), "El AMID ingresado no es válido.")

    def test_exportaciones_estandar_sin_registros_retornan_404(self):
        self.autenticar()
        for nombre in (
            "dashboard:exportar_baterias_excel",
            "dashboard:exportar_gps_excel",
        ):
            with self.subTest(view=nombre), patch(
                "apps.dashboard.views.crear_excel_completo_amid",
                return_value=None,
            ):
                response = self.client.get(reverse(nombre), {"amid": "7500001"})
                self.assertEqual(response.status_code, 404)
                self.assertIn("No existen registros para el AMID 7500001", response.content.decode())

    def test_exportaciones_estandar_con_error_retornan_500(self):
        self.autenticar()
        for nombre in (
            "dashboard:exportar_baterias_excel",
            "dashboard:exportar_gps_excel",
        ):
            with self.subTest(view=nombre), patch(
                "apps.dashboard.views.crear_excel_completo_amid",
                side_effect=RuntimeError("Oracle sintético no disponible"),
            ):
                response = self.client.get(reverse(nombre), {"amid": "7500001"})
                self.assertEqual(response.status_code, 500)
                self.assertEqual(
                    response.content.decode(),
                    "Error consultando datos en Oracle: Oracle sintético no disponible",
                )

    def test_exportaciones_estandar_exitosas_retornan_xlsx_y_filename(self):
        self.autenticar()
        for nombre in (
            "dashboard:exportar_baterias_excel",
            "dashboard:exportar_gps_excel",
        ):
            with self.subTest(view=nombre), patch(
                "apps.dashboard.views.crear_excel_completo_amid",
                side_effect=lambda **kwargs: Workbook(),
            ), patch(
                "apps.dashboard.views.obtener_ahora_referencia",
                return_value=self.AHORA,
            ):
                response = self.client.get(reverse(nombre), {"amid": "7500001"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response["Content-Type"],
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                self.assertEqual(
                    response["Content-Disposition"],
                    'attachment; filename="datos_amid_7500001_14_dias_20260911_123456.xlsx"',
                )
                self.assertTrue(response.content.startswith(b"PK"))

    def test_exportacion_alertas_exitosa_retorna_xlsx_y_filename(self):
        self.autenticar()
        with patch(
            "apps.dashboard.views.obtener_alertas_para_exportar",
            return_value=[],
        ), patch(
            "apps.dashboard.views.crear_excel_alertas",
            return_value=Workbook(),
        ), patch(
            "apps.dashboard.views.obtener_ahora_referencia",
            return_value=self.AHORA,
        ):
            response = self.client.get(reverse("dashboard:exportar_alertas_excel"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="panel_alertas_20260911_123456.xlsx"',
        )
        self.assertTrue(response.content.startswith(b"PK"))

    def test_detalle_caidas_rechaza_metodo_no_get(self):
        self.autenticar()
        response = self.client.post(reverse("dashboard:detalle_caidas_bateria"))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json(), {"detalle": "Metodo no permitido."})

    def test_detalle_caidas_rechaza_amid_no_numerico(self):
        self.autenticar()
        response = self.client.get(
            reverse("dashboard:detalle_caidas_bateria"), {"amid": "ABC"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detalle": "Debes indicar un AMID valido."})

    def test_detalle_caidas_retorna_resultado_del_servicio(self):
        self.autenticar()
        resultado = {"total": 1, "alertas": [{"diferencia": -20}]}
        with patch(
            "apps.dashboard.views.obtener_detalle_caidas_bateria_oracle",
            return_value=resultado,
        ) as mock_detalle:
            response = self.client.get(
                reverse("dashboard:detalle_caidas_bateria"), {"amid": "7500001"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), resultado)
        mock_detalle.assert_called_once_with(amid="7500001", dias=14)

    def test_detalle_caidas_retorna_503_si_servicio_falla(self):
        self.autenticar()
        with patch(
            "apps.dashboard.views.obtener_detalle_caidas_bateria_oracle",
            side_effect=RuntimeError("Oracle sintético no disponible"),
        ):
            response = self.client.get(
                reverse("dashboard:detalle_caidas_bateria"), {"amid": "7500001"}
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detalle": "El detalle de caidas de Oracle no esta disponible."},
        )

    def test_accion_admin_rechaza_usuario_sin_permiso(self):
        self.autenticar()
        response = self.client.post(
            reverse("dashboard:ejecutar_comando_admin"), {"accion": "probar_oracle"}
        )

        self.assertRedirects(
            response, reverse("dashboard:panel_perfil"), fetch_redirect_response=False
        )
        self.assertIn("No tienes permisos para ejecutar acciones administrativas.", self.mensajes(response))

    def test_accion_admin_requiere_post(self):
        self.autenticar(admin=True)
        with patch("apps.dashboard.views.call_command") as mock_comando:
            response = self.client.get(reverse("dashboard:ejecutar_comando_admin"))

        self.assertRedirects(
            response, reverse("dashboard:panel_perfil"), fetch_redirect_response=False
        )
        mock_comando.assert_not_called()

    def test_importacion_admin_exige_archivo(self):
        self.autenticar(admin=True)
        with patch("apps.dashboard.views.call_command") as mock_comando:
            response = self.client.post(
                reverse("dashboard:ejecutar_comando_admin"),
                {"accion": "importar_ubicaciones"},
            )

        self.assertRedirects(
            response, reverse("dashboard:panel_perfil"), fetch_redirect_response=False
        )
        self.assertIn("Debes seleccionar un archivo Excel.", self.mensajes(response))
        mock_comando.assert_not_called()

    def test_admin_autorizado_ejecuta_accion_mediante_command_mock(self):
        self.autenticar(admin=True)
        with patch("apps.dashboard.views.call_command") as mock_comando:
            response = self.client.post(
                reverse("dashboard:ejecutar_comando_admin"), {"accion": "probar_oracle"}
            )

        self.assertRedirects(
            response, reverse("dashboard:panel_perfil"), fetch_redirect_response=False
        )
        mock_comando.assert_called_once()
        self.assertIn("Proceso ejecutado correctamente.", self.mensajes(response))

    def test_archivo_temporal_se_elimina_aunque_command_falle(self):
        self.autenticar(admin=True)
        archivo = SimpleUploadedFile(
            "ubicaciones-sinteticas.xlsx", b"contenido sintetico", content_type="application/octet-stream"
        )
        with TemporaryDirectory() as directorio, override_settings(BASE_DIR=Path(directorio)):
            with patch(
                "apps.dashboard.views.call_command",
                side_effect=RuntimeError("fallo sintético del command"),
            ):
                response = self.client.post(
                    reverse("dashboard:ejecutar_comando_admin"),
                    {"accion": "importar_ubicaciones", "archivo_version_zp": archivo},
                )

            carpeta = Path(directorio) / "temp_uploads"
            self.assertTrue(carpeta.exists())
            self.assertEqual(list(carpeta.iterdir()), [])

        self.assertRedirects(
            response, reverse("dashboard:panel_perfil"), fetch_redirect_response=False
        )
        self.assertIn("Error ejecutando proceso: fallo sintético del command", self.mensajes(response))

    def test_editor_reglas_rechaza_metodo_incorrecto(self):
        self.autenticar(admin=True)
        response = self.client.post(reverse("dashboard:editor_reglas_alertas"))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.content.decode(), "Método no permitido.")

    def test_editor_reglas_retorna_403_sin_permiso(self):
        self.autenticar()
        response = self.client.get(reverse("dashboard:editor_reglas_alertas"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.content.decode(), "No tienes permisos para editar estas reglas."
        )

    def test_editor_reglas_retorna_503_si_servicio_falla(self):
        self.autenticar(admin=True)
        with patch(
            "apps.dashboard.views.obtener_editor_reglas_alertas",
            side_effect=RuntimeError("Oracle sintético no disponible"),
        ), patch(
            "apps.dashboard.views.recalculo_en_curso", return_value=False
        ), patch(
            "apps.dashboard.views.leer_log_recalculo", return_value=""
        ):
            response = self.client.get(reverse("dashboard:editor_reglas_alertas"))

        self.assertEqual(response.status_code, 503)
        self.assertTemplateUsed(response, "dashboard/partials/editor_reglas_alertas.html")
        self.assertEqual(
            response.context["reglas_alertas_error"], "Oracle sintético no disponible"
        )
