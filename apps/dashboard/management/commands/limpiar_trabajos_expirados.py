from django.core.management.base import BaseCommand

from apps.dashboard.services.trabajos import limpiar_expirados


class Command(BaseCommand):
    help = "Elimina archivos de trabajos expirados y conserva sus registros."

    def handle(self, *args, **options):
        cantidad = limpiar_expirados()
        self.stdout.write(f"Trabajos expirados limpiados: {cantidad}")
