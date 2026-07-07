from django.apps import AppConfig
from django.conf import settings
import os


class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard"

    def ready(self):
        """
        Antes el scheduler se iniciaba automáticamente al levantar Django.

        Ahora queda desactivado por defecto, porque:
        - Baterías consulta Oracle directo.
        - GPS consulta Oracle directo.
        - Ubicaciones esperadas se cargan manualmente desde Perfil.
        - SQLite queda principalmente para usuarios, sesiones y logs internos.
        """

        if os.environ.get("RUN_MAIN") != "true":
            return

        if not getattr(settings, "DASHBOARD_SCHEDULER_ENABLED", False):
            return

        from apps.dashboard.services.scheduler import iniciar_scheduler

        iniciar_scheduler()