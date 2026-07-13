from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Comando antiguo deshabilitado. La limpieza SQLite operativa ya no aplica."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "Este comando está deshabilitado. "
                "La limpieza de EstadoValidadorLimpio ya no aplica porque "
                "los datos operativos ahora están en Oracle."
            )
        )