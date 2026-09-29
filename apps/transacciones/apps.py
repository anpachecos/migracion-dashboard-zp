from django.apps import AppConfig


class TransaccionesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.transacciones"
    verbose_name = "Transacciones"

    def ready(self):
        """
        El módulo de Transacciones no inicia procesos en segundo plano.

        No hay modelos propios, no hay migraciones y no hay jobs: todo el acceso
        a datos es una consulta READ-ONLY a Oracle desde el repositorio, y solo
        cuando `TRX_ORACLE_HABILITADO` está habilitado.
        """
