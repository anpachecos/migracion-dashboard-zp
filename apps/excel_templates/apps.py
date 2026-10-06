from django.apps import AppConfig


class ExcelTemplatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.excel_templates"
    verbose_name = "Plantillas Excel"

    def ready(self):
        """
        El motor de plantillas Excel no inicia procesos en segundo plano.

        No hay tareas programadas ni senales externos: la captura de plantillas
        es una operacion explicita (management command o endpoint de
        desarrollo) y la exportacion se atiende por peticion.
        """