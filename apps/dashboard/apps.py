import os

from django.apps import AppConfig
from django.conf import settings


class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard"

    def ready(self):
        """
        Inicializa procesos internos de la app dashboard.

        El scheduler se inicia solo si DASHBOARD_SCHEDULER_ENABLED=True.
        Actualmente debe usarse solo para tareas automáticas internas, como:
        - registrar estado de Oracle;
        - limpiar historial de ubicaciones Oracle.

        La carga de ubicaciones esperadas se realiza manualmente desde el panel
        Perfil, mediante la subida de un archivo Excel por parte de un usuario admin.

        La validación con RUN_MAIN evita duplicar el scheduler cuando Django
        se ejecuta con runserver en modo desarrollo.
        """

        if os.environ.get("RUN_MAIN") != "true":
            return

        if not getattr(settings, "DASHBOARD_SCHEDULER_ENABLED", False):
            return

        from apps.dashboard.services.scheduler import iniciar_scheduler

        iniciar_scheduler()