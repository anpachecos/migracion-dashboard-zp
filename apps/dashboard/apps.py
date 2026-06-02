from django.apps import AppConfig
import os


class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard"
    
    def ready(self):
        if os.environ.get("RUN_MAIN") != "true":
            return

        from apps.dashboard.services.scheduler import iniciar_scheduler

        iniciar_scheduler()