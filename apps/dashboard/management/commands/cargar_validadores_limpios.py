from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Comando antiguo deshabilitado. El flujo actual usa Oracle directo."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "Este comando está deshabilitado. "
                "El flujo antiguo de carga a EstadoValidadorLimpio ya no se usa. "
                "Los datos operativos ahora se consultan directamente desde Oracle."
            )
        )