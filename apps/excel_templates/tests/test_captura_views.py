"""
Pruebas de la captura de plantillas por HTTP.

Es la operacion que dispara el boton **Importar plantilla** del monitor, y es
la unica del modulo que escribe en la base. Lo que se fija aca:

- El permiso. Ver transacciones no es lo mismo que poder capturar: una `SONDA`
  descarga la plantilla vigente pero no crea versiones. Superusuario y `Admin`
  si pueden.
- Los dos modos del dialogo: actualizar una plantilla existente
  (`plantilla_id`) o crear una nueva (`nombre`).
- Que una version en borrador **no** reemplaza a la vigente.
- Que un archivo ya capturado se rechaza con 409, no con un 400 generico: la
  accion que corresponde es elegir otra plantilla, y el dialogo lo distingue.
"""

import json
import io
import zipfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.excel_templates import models, services
from apps.dashboard.models import TrabajoArchivo

from .generador import construir as construir_sintetico

CLOAVE = "clave-de-prueba-123"

RUTA_CAPTURA = "/plantillas-excel/capturar/"

PERMISOS = {"TRX_GRUPOS_PERMITIDOS": ("Admin", "SONDA")}


def archivo_nuevo(nombre_hoja="Datos", sufijo=".xlsx"):
    """
    Ruta a un `.xlsx` valido y distinto del primero.

    El generador escribe el archivo segun el nombre de su hoja, asi que cambiar
    ese nombre da bytes distintos: es lo que hace que el SHA no coincida y la
    prueba de duplicado no se dispare por casualidad.
    """

    import tempfile

    mango, ruta = tempfile.mkstemp(suffix=sufijo)
    # En Windows el descriptor abierto impide abrir el mismo archivo por
    # escritura, que es lo que hace el generador.
    import os

    os.close(mango)

    return construir_sintetico(ruta, hoja_datos=nombre_hoja)


def crear_superusuario(username="super_captura"):
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


def subir(ruta, nombre="ZONA_PAGA_V764_MARTES.XLSX"):
    """El archivo a POST, leido de la ruta del temporal."""

    with open(ruta, "rb") as archivo:
        contenido = archivo.read()

    return SimpleUploadedFile(nombre, contenido)


class AutorizacionDeCapturaTests(TestCase):
    """Capturar exige mas permiso que ver transacciones."""

    @override_settings(EXCEL_TEMPLATES_GRUPOS_CAPTURA=("Admin",))
    def test_un_anonimo_recibe_302_a_login(self):
        with self.settings(**PERMISOS):
            respuesta = self.client.post(RUTA_CAPTURA)

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith("/login/?next="))

    @override_settings(EXCEL_TEMPLATES_GRUPOS_CAPTURA=("Admin",))
    def test_una_sonda_puede_ver_pero_no_capturar(self):
        """La SONDA entra al monitor y recibe 403 al subir."""

        self.client.force_login(crear_de_grupo("sonda_captura", "SONDA"))

        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA, {"nombre": "X", "archivo": subir(archivo_nuevo("Otra"))}
            )

        self.assertEqual(respuesta.status_code, 403)


    @override_settings(EXCEL_TEMPLATES_GRUPOS_CAPTURA=("Admin",))
    def test_una_sonda_tampoco_puede_solo_por_ver_transacciones(self):
        """Mensaje de permiso de captura, no el de lectura: son gates distintos."""

        self.client.force_login(crear_de_grupo("sonda_permiso", "SONDA"))

        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA, {"nombre": "X", "archivo": subir(archivo_nuevo("Otra"))}
            )

        self.assertEqual(respuesta.status_code, 403)


    @override_settings(EXCEL_TEMPLATES_GRUPOS_CAPTURA=())
    def test_lista_vacia_deja_la_captura_solo_para_superusuarios(self):
        """Fallo seguro: sin grupos configurados no se escribe."""

        self.client.force_login(crear_de_grupo("admin_captura", "Admin"))

        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA, {"nombre": "X", "archivo": subir(archivo_nuevo("Otra"))}
            )

        self.assertEqual(respuesta.status_code, 403)


    @override_settings(EXCEL_TEMPLATES_GRUPOS_CAPTURA=("Admin",))
    def test_un_admin_si_puede_capturar(self):
        self.client.force_login(crear_de_grupo("admin_ok", "Admin"))

        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {"nombre": "Version Zona Paga", "archivo": subir(archivo_nuevo("Otra"))},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(models.Template.objects.count(), 1)

    @override_settings(EXCEL_TEMPLATES_GRUPOS_CAPTURA=("Admin",))
    def test_un_superusuario_puede_aunque_no_este_en_ningun_grupo(self):
        self.client.force_login(crear_superusuario())

        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {"nombre": "Version Zona Paga", "archivo": subir(archivo_nuevo("Otra"))},
            )

        self.assertEqual(respuesta.status_code, 200)

    @override_settings(EXCEL_TEMPLATES_GRUPOS_CAPTURA=("Admin",))
    def test_quien_no_ve_transacciones_tampoco_captura(self):
        """Sin acceso al monitor no hay captura: es el primer gate."""

        self.client.force_login(
            get_user_model().objects.create_user(
                username="nada_captura", password=CLOAVE
            )
        )

        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA, {"nombre": "X", "archivo": subir(archivo_nuevo("Otra"))}
            )

        self.assertEqual(respuesta.status_code, 403)


class CapturaSegundoPlanoTests(TestCase):
    """La interfaz puede encolar la captura sin mantener abierta la request."""

    def setUp(self):
        self.ruta = archivo_nuevo("Async")
        self.usuario = crear_superusuario("super_async")
        self.client.force_login(self.usuario)

    def test_captura_async_persiste_el_archivo_y_responde_202(self):
        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {
                    "nombre": "Plantilla asíncrona",
                    "archivo": subir(self.ruta),
                    "segundo_plano": "1",
                },
            )

        self.assertEqual(respuesta.status_code, 202)
        self.assertFalse(models.Template.objects.exists())
        trabajo = TrabajoArchivo.objects.get(tipo="PLANTILLA_IMPORTAR")
        self.assertEqual(trabajo.estado, TrabajoArchivo.Estado.PENDIENTE)
        self.assertTrue(trabajo.archivo_entrada.name)


class CapturaComoCrearOActualizarTests(TestCase):
    """Las dos opciones del dialogo."""

    def setUp(self):
        self.ruta = archivo_nuevo()
        self.usuario = crear_superusuario("super_destino")
        self.client.force_login(self.usuario)

    def _capturar(self, **campos):
        with self.settings(**PERMISOS):
            return self.client.post(
                RUTA_CAPTURA,
                {"archivo": subir(self.ruta), **campos},
            )

    def test_crear_una_plantilla_nueva(self):
        respuesta = self._capturar(nombre="Version Zona Paga")

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()

        self.assertTrue(datos["creada"])
        self.assertEqual(datos["nombre"], "Version Zona Paga")
        self.assertEqual(datos["version"], 1)
        self.assertTrue(datos["vigente"])
        # El nombre de descarga sale del archivo tal cual, con la extension en
        # minuscula: el motor no reescribe el nombre real del Excel.
        self.assertEqual(datos["archivo"], "ZONA_PAGA_V764_MARTES.xlsx")

    def test_acepta_xlsm_y_lo_captura_sin_error(self):
        """La extension .xlsm es valida para importar aunque exporte como xlsx."""

        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {
                    "nombre": "Libro habilitado para macros",
                    # Es un ZIP xlsx valido con extension xlsm: basta para
                    # verificar el contrato de extension/lectura sin exigir
                    # tener un proyecto VBA real en las pruebas.
                    "archivo": subir(self.ruta, "Libro.XLSM"),
                },
            )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        version = models.TemplateVersion.objects.get()
        self.assertEqual(version.source_ext, ".xlsm")
        self.assertEqual(respuesta.json()["archivo"], "Libro.xlsx")

    def test_crear_sin_nombre_falla_con_400(self):
        respuesta = self._capturar()

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(models.Template.objects.count(), 0)

    def test_el_valor_visual_nueva_crea_la_plantilla(self):
        """El radio del dialogo puede enviar `plantilla_id=nueva`."""

        respuesta = self._capturar(
            nombre="Creada desde el dialogo", plantilla_id="nueva"
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertTrue(respuesta.json()["creada"])
        self.assertEqual(
            models.Template.objects.get().name, "Creada desde el dialogo"
        )

    def test_actualizar_una_plantilla_existente_crea_la_version_siguiente(self):
        plantilla = models.Template.objects.create(
            name="Version Zona Paga", export_filename="ZONA_PAGA_V764_MARTES.xlsx"
        )
        primera = models.TemplateVersion.objects.create(
            template=plantilla,
            version_no=1,
            source_filename="viejo.xlsx",
            source_sha256="a" * 64,
            status=models.TemplateVersion.Status.VIGENTE,
        )
        plantilla.current_version = primera
        plantilla.save(update_fields=["current_version"])

        # El archivo tiene que ser distinto: el mismo SHA se rechaza.
        segunda_ruta = archivo_nuevo("Otra")
        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {
                    "archivo": subir(segunda_ruta, "OTRA.XLSX"),
                    "plantilla_id": plantilla.id,
                },
            )

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()

        self.assertEqual(datos["version"], 2)
        self.assertFalse(datos["creada"])
        self.assertTrue(datos["vigente"])

    def test_actualizar_no_renombra_la_plantilla(self):
        """
        El nombre y el nombre de descarga se deciden al crear. Si cambiaran en
        cada captura, un enlace ya compartido bajaria otro archivo.
        """

        plantilla = models.Template.objects.create(
            name="Version Zona Paga", export_filename="ZONA_PAGA_V764_MARTES.xlsx"
        )

        segunda_ruta = archivo_nuevo("Otra")
        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {
                    "archivo": subir(segunda_ruta, "OTRO_ARCHIVO.XLSX"),
                    "plantilla_id": plantilla.id,
                    # Even el nombre del formulario dice otra cosa, la plantilla
                    # es la que se eligio.
                    "nombre": "Nombre que se ignora",
                },
            )

        self.assertEqual(respuesta.status_code, 200)
        plantilla.refresh_from_db()

        self.assertEqual(plantilla.name, "Version Zona Paga")
        self.assertEqual(plantilla.export_filename, "ZONA_PAGA_V764_MARTES.xlsx")
        self.assertEqual(models.Template.objects.count(), 1)

    def test_actualizar_una_plantilla_inexistente_da_404(self):
        respuesta = self._capturar(nombre="X", plantilla_id=999)

        self.assertEqual(respuesta.status_code, 404)

    def test_un_id_no_numerico_da_400(self):
        respuesta = self._capturar(plantilla_id="abc")

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("entero", respuesta.json()["error"])

    def test_un_nombre_que_ya_existe_agrega_una_version(self):
        """Elegir "nueva" con un nombre tomado no deja al usuario atascado."""

        models.Template.objects.create(
            name="Version Zona Paga", export_filename="ZONA_PAGA_V764_MARTES.xlsx"
        )

        respuesta = self._capturar(nombre="Version Zona Paga")

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()

        self.assertFalse(datos["creada"])
        self.assertEqual(datos["version"], 1)
        self.assertEqual(models.Template.objects.count(), 1)

    def test_sin_archivo_da_400(self):
        with self.settings(**PERMISOS):
            respuesta = self.client.post(RUTA_CAPTURA, {"nombre": "X"})

        self.assertEqual(respuesta.status_code, 400)

    def test_una_extension_no_permitida_da_400(self):
        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {"nombre": "X", "archivo": subir(self.ruta, "plantilla.txt")},
            )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("xlsx", respuesta.json()["error"])


class PublicarYBorradorTests(TestCase):
    """La casilla "dejar esta versión como la vigente"."""

    def setUp(self):
        self.ruta = archivo_nuevo()
        self.client.force_login(crear_superusuario("super_borrador"))

    def test_sin_publicar_la_version_queda_en_borrador(self):
        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {"nombre": "Version Zona Paga", "archivo": subir(self.ruta), "publicar": "0"},
            )

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()

        self.assertFalse(datos["vigente"])
        self.assertEqual(datos["version"], 1)

        plantilla = models.Template.objects.get()
        version = plantilla.versions.get()

        self.assertEqual(version.status, models.TemplateVersion.Status.BORRADOR)
        # Sin `current_version` no hay nada que descargar todavia, y la lista
        # de plantillas no la muestra.
        self.assertIsNone(plantilla.current_version)

    def test_actualizar_en_borrador_no_mueve_la_vigente(self):
        plantilla = models.Template.objects.create(
            name="Version Zona Paga", export_filename="ZONA_PAGA_V764_MARTES.xlsx"
        )
        vigente = models.TemplateVersion.objects.create(
            template=plantilla,
            version_no=1,
            source_filename="viejo.xlsx",
            source_sha256="a" * 64,
            status=models.TemplateVersion.Status.VIGENTE,
        )
        plantilla.current_version = vigente
        plantilla.save(update_fields=["current_version"])

        segunda = archivo_nuevo("Otra")
        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {"plantilla_id": plantilla.id, "archivo": subir(segunda), "publicar": "0"},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.json()["vigente"])

        plantilla.refresh_from_db()
        plantilla.versions.get(version_no=1).refresh_from_db()

        self.assertEqual(plantilla.current_version_id, vigente.id)
        self.assertEqual(
            plantilla.versions.get(version_no=1).status,
            models.TemplateVersion.Status.VIGENTE,
        )


class ArchivoDuplicadoTests(TestCase):
    """Un archivo identico a uno ya capturado no crea nada."""

    def setUp(self):
        self.ruta = archivo_nuevo()
        self.client.force_login(crear_superusuario("super_duplicado"))

    def test_rechaza_el_mismo_archivo_con_409(self):
        with self.settings(**PERMISOS):
            primera = self.client.post(
                RUTA_CAPTURA,
                {"nombre": "Version Zona Paga", "archivo": subir(self.ruta)},
            )
            segunda = self.client.post(
                RUTA_CAPTURA,
                {"nombre": "Otra plantilla", "archivo": subir(self.ruta)},
            )

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 409)

        datos = segunda.json()

        self.assertEqual(datos["codigo"], "plantilla_duplicada")
        # El mensaje dice donde esta, para que la accion sea elegir esa.
        self.assertIn("Version Zona Paga", datos["error"])
        self.assertIn("version 1", datos["error"])

        self.assertEqual(models.TemplateVersion.objects.count(), 1)
        self.assertEqual(models.Template.objects.count(), 1)

    def test_el_409_no_es_un_error_de_servidor(self):
        with self.settings(**PERMISOS):
            self.client.post(
                RUTA_CAPTURA,
                {"nombre": "Version Zona Paga", "archivo": subir(self.ruta)},
            )
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {"nombre": "Otra", "archivo": subir(self.ruta)},
            )

        # 409 y no 500: el archivo no es invalido, ya esta capturado.
        self.assertLess(respuesta.status_code, 500)

    def test_un_archivo_distinto_si_se_acepta(self):
        with self.settings(**PERMISOS):
            self.client.post(
                RUTA_CAPTURA,
                {"nombre": "Version Zona Paga", "archivo": subir(self.ruta)},
            )

        otro = archivo_nuevo("Otra")
        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {"nombre": "Otra", "archivo": subir(otro, "OTRA.XLSX")},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(models.TemplateVersion.objects.count(), 2)


class ListaParaElDialogoTests(TestCase):
    """Lo que el dialogo de exportar recibe por `GET /plantillas-excel/`."""

    def setUp(self):
        self.client.force_login(crear_superusuario("super_lista"))

    def test_lista_vacia_no_es_un_error(self):
        with self.settings(**PERMISOS):
            respuesta = self.client.get(reverse("excel_templates:listar"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"plantillas": []})

    def test_una_plantilla_sin_version_no_aparece(self):
        """Sin version vigente no hay nada que descargar."""

        models.Template.objects.create(
            name="Sin capturar", export_filename="SIN_CAPTURAR.xlsx"
        )

        with self.settings(**PERMISOS):
            respuesta = self.client.get(reverse("excel_templates:listar"))

        self.assertEqual(respuesta.json()["plantillas"], [])

    def test_publica_lo_que_el_dialogo_necesita(self):
        plantilla = models.Template.objects.create(
            name="Version Zona Paga", export_filename="ZONA_PAGA_V764_MARTES.xlsx"
        )
        version = models.TemplateVersion.objects.create(
            template=plantilla,
            version_no=1,
            source_filename="origen.xlsx",
            source_sha256="a" * 64,
            status=models.TemplateVersion.Status.VIGENTE,
        )
        plantilla.current_version = version
        plantilla.save(update_fields=["current_version"])

        with self.settings(**PERMISOS):
            respuesta = self.client.get(reverse("excel_templates:listar"))

        fila = respuesta.json()["plantillas"][0]

        self.assertEqual(
            set(fila),
            {"id", "nombre", "archivo", "version", "actualizada"},
        )
        self.assertEqual(fila["nombre"], "Version Zona Paga")
        self.assertEqual(fila["version"], 1)
        json.dumps(fila)


class ExportarDesdeLaVistaTests(TestCase):
    """La descarga HTTP debe ser un XLSX valido, no una pagina HTML."""

    def setUp(self):
        self.ruta = archivo_nuevo("Exportar")
        self.client.force_login(crear_superusuario("super_exportar"))

        with self.settings(**PERMISOS):
            respuesta = self.client.post(
                RUTA_CAPTURA,
                {
                    "nombre": "Plantilla para exportar",
                    "archivo": subir(self.ruta, "Plantilla.XLSX"),
                },
            )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.plantilla = models.Template.objects.get()

    def test_descarga_un_zip_xlsx_con_mime_y_nombre_correctos(self):
        with self.settings(**PERMISOS):
            respuesta = self.client.get(
                reverse(
                    "excel_templates:exportar",
                    args=[self.plantilla.pk],
                )
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("Plantilla.xlsx", respuesta["Content-Disposition"])
        self.assertTrue(respuesta.content.startswith(b"PK"))

        with zipfile.ZipFile(io.BytesIO(respuesta.content)) as archivo:
            self.assertIsNone(archivo.testzip())
            self.assertIn("xl/styles.xml", archivo.namelist())

        from openpyxl import load_workbook

        libro = load_workbook(io.BytesIO(respuesta.content), data_only=False)
        hoja = libro["Exportar"]

        # Los datos se vacian, pero el estilo de la cabecera se conserva.
        self.assertIsNone(hoja["A2"].value)
        self.assertTrue(hoja["A1"].font.bold)
        self.assertEqual(hoja["A1"].fill.fill_type, "solid")
        self.assertEqual(hoja["A1"].border.left.style, "thin")
        libro.close()

    def test_la_descarga_vacia_de_la_ui_quita_tambien_las_etiquetas(self):
        """`keep_labels=0` vacia el texto sin perder el formato."""

        with self.settings(**PERMISOS):
            respuesta = self.client.get(
                reverse("excel_templates:exportar", args=[self.plantilla.pk])
                + "?keep_labels=0"
            )

        from openpyxl import load_workbook

        libro = load_workbook(io.BytesIO(respuesta.content), data_only=False)
        hoja = libro["Exportar"]

        for fila in hoja.iter_rows():
            for celda in fila:
                self.assertIsNone(celda.value, celda.coordinate)

        self.assertTrue(hoja["A1"].font.bold)
        self.assertEqual(hoja["A1"].fill.fill_type, "solid")
        libro.close()


class EditarPlantillaTests(TestCase):
    """El panel Admin cambia metadatos sin mutar versiones."""

    def setUp(self):
        self.usuario = crear_superusuario("super_editor")
        self.client.force_login(self.usuario)
        self.plantilla = models.Template.objects.create(
            name="Versión Zona Paga",
            export_filename="ZONA_PAGA.xlsx",
            description="Formato original",
        )
        self.version = models.TemplateVersion.objects.create(
            template=self.plantilla,
            version_no=1,
            source_filename="origen.xlsx",
            source_sha256="b" * 64,
            status=models.TemplateVersion.Status.VIGENTE,
        )
        self.plantilla.current_version = self.version
        self.plantilla.save(update_fields=["current_version"])

    def test_admin_puede_editar_metadatos(self):
        respuesta = self.client.post(
            reverse("excel_templates:editar", args=[self.plantilla.pk]),
            {
                "nombre": "Versión Zona Paga Principal",
                "export_filename": "version-zona-paga.xlsx",
                "descripcion": "Formato actualizado",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.plantilla.refresh_from_db()
        self.assertEqual(self.plantilla.name, "Versión Zona Paga Principal")
        self.assertEqual(self.plantilla.export_filename, "version-zona-paga.xlsx")
        self.assertEqual(self.plantilla.description, "Formato actualizado")
        self.assertEqual(self.plantilla.versions.count(), 1)

    def test_el_nombre_del_archivo_se_normaliza_a_xlsx(self):
        services.editar_metadatos(
            self.plantilla,
            nombre="Versión Zona Paga",
            export_filename="version-zona-paga.xlsm",
        )

        self.plantilla.refresh_from_db()
        self.assertEqual(self.plantilla.export_filename, "version-zona-paga.xlsx")

    def test_no_se_permite_nombre_duplicado(self):
        models.Template.objects.create(
            name="Otra plantilla",
            export_filename="otra.xlsx",
        )

        respuesta = self.client.post(
            reverse("excel_templates:editar", args=[self.plantilla.pk]),
            {
                "nombre": "Otra plantilla",
                "export_filename": "version-zona-paga.xlsx",
            },
        )

        self.assertEqual(respuesta.status_code, 400)
        self.plantilla.refresh_from_db()
        self.assertEqual(self.plantilla.name, "Versión Zona Paga")
