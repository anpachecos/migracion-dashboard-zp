from unittest.mock import patch

from django.test import SimpleTestCase

from apps.dashboard.management.commands.iniciar_dashboard import Command as Launcher
from apps.dashboard.management.commands.ejecutar_scheduler import Command as Scheduler


class LauncherTests(SimpleTestCase):
    def test_desarrollo_usa_runserver_sin_autoreload(self):
        comandos = dict(Launcher()._comandos("development", "127.0.0.1", "8000"))

        self.assertEqual(comandos["web"][-1], "--noreload")
        self.assertEqual(comandos["worker"][-2:], ["manage.py", "procesar_trabajos"])
        self.assertEqual(comandos["scheduler"][-2:], ["manage.py", "ejecutar_scheduler"])

    def test_produccion_usa_waitress(self):
        comandos = dict(Launcher()._comandos("production", "0.0.0.0", "8080"))

        self.assertIn("waitress", comandos["web"])
        self.assertIn("--listen=0.0.0.0:8080", comandos["web"])
        self.assertIn("config.wsgi:application", comandos["web"])


class SchedulerCommandTests(SimpleTestCase):
    def test_scheduler_se_detiene_con_keyboard_interrupt(self):
        comando = Scheduler()
        with patch(
            "apps.dashboard.management.commands.ejecutar_scheduler.scheduler.iniciar_scheduler"
        ) as iniciar, patch(
            "apps.dashboard.management.commands.ejecutar_scheduler.time.sleep",
            side_effect=KeyboardInterrupt,
        ):
            comando.handle()

        iniciar.assert_called_once_with()
