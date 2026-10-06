import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.dashboard.models import TrabajoArchivo
from apps.dashboard.services.trabajos import (
    crear_trabajo,
    marcar_interrumpidos,
    procesar_trabajo,
)


class TrabajoArchivoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser("trabajos", password="x")
        self.otro = get_user_model().objects.create_user("otro", password="x")
        self.client.force_login(self.usuario)

    def test_crear_trabajo_responde_202_y_persiste_parametros(self):
        respuesta = self.client.post(
            reverse("dashboard:crear_trabajo_archivo"),
            {
                "tipo": "TRX_REZAGADAS",
                "parametros": json.dumps({"fecha_desde": "2026-08-27"}),
            },
        )

        self.assertEqual(respuesta.status_code, 202)
        trabajo = TrabajoArchivo.objects.get()
        self.assertEqual(trabajo.estado, TrabajoArchivo.Estado.PENDIENTE)
        self.assertEqual(trabajo.parametros_json["fecha_desde"], "2026-08-27")

    def test_tipo_desconocido_no_se_encola(self):
        respuesta = self.client.post(
            reverse("dashboard:crear_trabajo_archivo"),
            {"tipo": "NO_EXISTE", "parametros": "{}"},
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(TrabajoArchivo.objects.exists())

    def test_estado_no_entrega_contenido_del_archivo(self):
        trabajo = crear_trabajo(self.usuario, "TRX_REZAGADAS")
        respuesta = self.client.get(reverse("dashboard:estado_trabajos_archivo"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["trabajos"][0]["id"], trabajo.pk)
        self.assertNotIn("contenido", respuesta.json()["trabajos"][0])

    @override_settings(MEDIA_ROOT=Path(tempfile.mkdtemp()))
    def test_worker_guarda_archivo_y_descarga_solo_para_su_usuario(self):
        trabajo = crear_trabajo(self.usuario, "TRX_REZAGADAS")

        with patch(
            "apps.dashboard.services.trabajos._generador",
            return_value=lambda parametros, trabajo=None: {
                "contenido": b"xlsx",
                "nombre": "rezagadas.xlsx",
            },
        ):
            procesar_trabajo(trabajo)

        trabajo.refresh_from_db()
        self.assertEqual(trabajo.estado, TrabajoArchivo.Estado.LISTO)
        self.assertTrue(trabajo.archivo.name)
        respuesta = self.client.get(
            reverse("dashboard:descargar_trabajo", args=[trabajo.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(b"".join(respuesta.streaming_content), b"xlsx")

        self.client.force_login(self.otro)
        self.assertEqual(
            self.client.get(
                reverse("dashboard:descargar_trabajo", args=[trabajo.pk])
            ).status_code,
            404,
        )

    def test_reinicio_marca_procesando_como_error(self):
        trabajo = crear_trabajo(self.usuario, "TRX_REZAGADAS")
        trabajo.estado = TrabajoArchivo.Estado.PROCESANDO
        trabajo.save(update_fields=["estado"])

        self.assertEqual(marcar_interrumpidos(), 1)
        trabajo.refresh_from_db()
        self.assertEqual(trabajo.estado, TrabajoArchivo.Estado.ERROR)
