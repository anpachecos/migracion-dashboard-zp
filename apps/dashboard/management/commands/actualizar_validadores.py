from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.models import LogImportacion


class Command(BaseCommand):
    help = "Actualiza validadores ejecutando importación Oracle, carga limpia y limpieza de antiguos"

    def handle(self, *args, **options):
        inicio = timezone.now()

        self.stdout.write("Iniciando actualización completa de validadores...")

        try:
            self.stdout.write("1/3 Importando datos desde Oracle...")
            call_command("importar_validadores_oracle")

            self.stdout.write("2/3 Cargando datos desde Raw hacia Limpio...")
            call_command("cargar_validadores_limpios")

            self.stdout.write("3/3 Eliminando registros antiguos...")
            call_command("limpiar_registros_antiguos")

            fin = timezone.now()
            duracion = fin - inicio

            self.stdout.write(
                self.style.SUCCESS(
                    f"Actualización completa finalizada correctamente. Duración: {duracion}"
                )
            )

        except Exception as error:
            LogImportacion.objects.create(
                origen="LIMPIEZA",
                estado="ERROR",
                fecha_inicio=inicio,
                fecha_fin=timezone.now(),
                mensaje=f"Error en actualización completa de validadores: {error}",
            )

            self.stderr.write(
                self.style.ERROR(
                    f"Error en actualización completa de validadores: {error}"
                )
            )