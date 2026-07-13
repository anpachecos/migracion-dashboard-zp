from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Comando antiguo deshabilitado. El flujo actual usa Oracle directo."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "Este comando está deshabilitado. "
                "La actualización antigua de validadores en SQLite ya no se usa. "
                "El dashboard consume datos desde Oracle y desde las tablas auxiliares Oracle."
            )
        )