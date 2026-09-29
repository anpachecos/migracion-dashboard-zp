from datetime import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.dashboard.services.horarios_zp_service import (
    crear_configuracion_horario_zp,
    filtrar_registros_por_horario_zp,
    obtener_columnas_media_hora_para_hoy,
)


class HorariosZonaPagaServiceTests(SimpleTestCase):
    def setUp(self):
        self.datos = {
            "NOMBRE": "Zona Paga de prueba",
            "HORARIO": "08:00 - 12:00",
            "HORARIO_LABORAL_PM": "14:00 – 18:00",
            "HORARIO_SABADO": None,
            "HORARIO_DOMINGO": "09:00 - 13:00",
        }

    def test_dia_habil_combina_tramos_am_y_pm(self):
        configuracion = crear_configuracion_horario_zp(
            self.datos,
            fecha_referencia=datetime(2026, 8, 24, 9, 0),
        )

        self.assertTrue(configuracion["tiene_horario_hoy"])
        self.assertEqual(
            configuracion["texto_hoy"],
            "08:00 a 12:00 · 14:00 a 18:00",
        )

        columnas = obtener_columnas_media_hora_para_hoy(configuracion)
        self.assertIn("08:00", columnas)
        self.assertIn("18:00", columnas)
        self.assertNotIn("13:00", columnas)

    def test_sabado_sin_horario_no_activa_filtro(self):
        configuracion = crear_configuracion_horario_zp(
            self.datos,
            fecha_referencia=datetime(2026, 8, 29, 9, 0),
        )

        self.assertFalse(configuracion["tiene_horario_hoy"])
        self.assertEqual(configuracion["texto_hoy"], "Sin horario asignado")

    def test_gps_filtra_por_dia_y_conserva_dias_sin_horario(self):
        configuracion = crear_configuracion_horario_zp(
            self.datos,
            fecha_referencia=datetime(2026, 8, 24, 9, 0),
        )
        registros = [
            SimpleNamespace(id=1, fecha_registro=datetime(2026, 8, 24, 9, 0)),
            SimpleNamespace(id=2, fecha_registro=datetime(2026, 8, 24, 13, 0)),
            SimpleNamespace(id=3, fecha_registro=datetime(2026, 8, 24, 15, 0)),
            SimpleNamespace(id=4, fecha_registro=datetime(2026, 8, 29, 22, 0)),
        ]

        filtrados, filtro_aplicado = filtrar_registros_por_horario_zp(
            registros,
            configuracion,
        )

        self.assertTrue(filtro_aplicado)
        self.assertEqual([registro.id for registro in filtrados], [1, 3, 4])
