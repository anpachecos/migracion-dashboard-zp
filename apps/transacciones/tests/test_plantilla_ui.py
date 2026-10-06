"""
Pruebas de la tarjeta de plantilla Excel del Monitor de Traspaso.

La tarjeta solo tiene dos botones que abren un dialogo. Lo que decide el
template es minimo, y por eso lo que se fija aca es lo que no debe romperse:

- Los dos botones se ven **siempre**, tambien con `DEBUG=False` y sin ninguna
  plantilla capturada. La captura paso a ser una funcionalidad real y ocultar
  el boton dejaria a la primera plantilla sin forma de subirla.
- La lista de plantillas no viaja en el HTML: la pide `plantilla.js` al abrir
  cada dialogo. Si volviera al contexto de la vista, el boton "Importar"
  prometeria algo que la pagina recien cargada no puede mostrar.
- El formulario de importacion lleva token de CSRF y apunta a la ruta de
  captura resuelta con `reverse`.

La lista de plantillas, los destinos y el envio se prueban del lado del
backend en `apps/excel_templates/tests/test_captura_views.py`.
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse

CLOAVE = "clave-de-prueba-123"


def crear_superusuario(username="plantillas_super"):
    return get_user_model().objects.create_superuser(
        username=username,
        email=f"{username}@example.test",
        password=CLOAVE,
    )


def crear_de_grupo(username, grupo):
    usuario = get_user_model().objects.create_user(
        username=username,
        password=CLOAVE,
    )
    existente, _ = Group.objects.get_or_create(name=grupo)
    usuario.groups.add(existente)
    return usuario


class TarjetaPlantillaTests(TestCase):
    """La tarjeta y sus dos dialogos."""

    def setUp(self):
        self.client.force_login(crear_superusuario())

    def _monitor(self):
        """Compatibilidad del nombre historico: ahora apunta al centro."""

        return self.client.get(reverse("transacciones:centro_archivos"))

    def _monitor_real(self):
        return self.client.get(reverse("transacciones:monitor"))

    def test_los_dos_botones_estan_siempre(self):
        contenido = self._monitor().content.decode()

        self.assertIn("Exportar plantilla", contenido)
        self.assertIn("Importar plantilla", contenido)

    def test_los_botones_no_dependen_del_modo_de_depuracion(self):
        """
        La captura es una funcion real, no una tarea de desarrollo. Con
        `DEBUG=False` los botones tienen que seguir ahi, porque la primera
        plantilla se sube en preproduccion.
        """

        with override_settings(DEBUG=False):
            contenido = self._monitor().content.decode()

        self.assertIn("Exportar plantilla", contenido)
        self.assertIn("Importar plantilla", contenido)

    def test_los_botones_no_dependen_de_que_haya_plantillas(self):
        """Sin plantillas el dialogo de exportar avisa; el boton no desaparece."""

        contenido = self._monitor().content.decode()

        self.assertIn("Exportar plantilla", contenido)
        self.assertIn("Importar plantilla", contenido)

    def test_hay_dos_dialogos(self):
        contenido = self._monitor().content.decode()

        self.assertIn("data-trx-dlg-exportar", contenido)
        self.assertIn("data-trx-dlg-importar", contenido)
        self.assertEqual(contenido.count("<dialog"), 3)

    def test_el_centro_de_archivos_muestra_los_reportes_mockup(self):
        contenido = self._monitor().content.decode()

        self.assertIn("Centro de archivos", contenido)
        self.assertIn("Versión Zona Paga", contenido)
        self.assertIn("Informe Interno TRX C2D", contenido)
        self.assertIn("TRX &gt;15 MIN", contenido)
        self.assertIn("TRX REZAGADAS", contenido)

    def test_el_centro_tiene_cola_no_bloqueante(self):
        contenido = self._monitor().content.decode()

        self.assertIn("data-trx-cola", contenido)
        self.assertIn("data-trx-reporte-periodicidad", contenido)
        self.assertIn("archivos_trx.js", contenido)

    def test_el_monitor_no_contiene_el_centro_de_archivos(self):
        contenido = self._monitor_real().content.decode()

        self.assertNotIn("data-trx-archivos", contenido)
        self.assertNotIn("trx-centro-archivos", contenido)

    def test_el_centro_admin_muestra_el_editor_y_el_historial(self):
        contenido = self._monitor().content.decode()

        self.assertIn("Editor de plantillas", contenido)
        self.assertIn("Solo Admin", contenido)
        self.assertIn("Todavía no hay plantillas", contenido)

    def test_el_formulario_de_importar_trae_token_de_csrf(self):
        """
        `plantilla.js` manda el formulario entero con `new FormData`. Si el
        token no esta dentro, el POST vuelve con 403 y el error no lo explica
        nada util.
        """

        contenido = self._monitor().content.decode()

        self.assertRegex(
            contenido,
            r'(?s)data-trx-form-importar.*?name="csrfmiddlewaretoken"',
        )

    def test_el_formulario_de_importar_apunta_a_la_ruta_de_captura(self):
        contenido = self._monitor().content.decode()

        self.assertRegex(
            contenido,
            r'action="' + re.escape(reverse("excel_templates:capturar")) + '"',
        )

    def test_las_urls_del_modulo_de_plantillas_llegan_en_la_tarjeta(self):
        contenido = self._monitor().content.decode()

        self.assertIn(f'data-url-plantillas="{reverse("excel_templates:listar")}"', contenido)
        self.assertIn(
            f'data-url-capturar="{reverse("excel_templates:capturar")}"', contenido
        )
        self.assertIn(
            'data-url-exportar="'
            + reverse("excel_templates:exportar", args=[0])
            + "?keep_labels=0\"",
            contenido,
        )

    def test_la_lista_de_plantillas_no_viaja_en_el_html(self):
        """
        La lista la pide el navegador al abrir el dialogo. Si volviera en el
        contexto, habria que recargar para ver el resultado de una importacion.
        """

        contenido = self._monitor().content.decode()

        self.assertNotIn("plantillas_excel", contenido)

    def test_el_boton_de_importar_lo_ve_tambien_quien_no_puede_capturar(self):
        """
        Los dos botones se ven siempre, como se pidio. Quien no tiene permiso
        recibe el 403 con su mensaje al enviar, no un boton que no existe.
        """

        self.client.force_login(crear_de_grupo("sonda_ui", "SONDA"))

        with override_settings(TRX_GRUPOS_PERMITIDOS=("Admin", "SONDA")):
            contenido = self._monitor().content.decode()

        self.assertIn("Importar plantilla", contenido)
