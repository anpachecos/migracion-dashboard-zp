from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.models import (
    EstadoValidadorRaw,
    EstadoValidadorLimpio,
    LogImportacion,
)


class Command(BaseCommand):
    help = "Elimina registros RAW y Limpio con fecha_hora mayor a 14 días de antigüedad"

    def handle(self, *args, **options):
        fecha_inicio = timezone.now()

        log = LogImportacion.objects.create(
            origen="LIMPIEZA",
            estado="OK",
            fecha_inicio=fecha_inicio,
            mensaje="Limpieza de registros antiguos iniciada",
        )

        try:
            limite = timezone.now() - timedelta(days=14)

            eliminados_raw, _ = EstadoValidadorRaw.objects.filter(
                fecha_hora__lt=limite
            ).delete()

            eliminados_limpio, _ = EstadoValidadorLimpio.objects.filter(
                fecha_hora__lt=limite
            ).delete()

            total_eliminados = eliminados_raw + eliminados_limpio

            log.estado = "OK"
            log.fecha_fin = timezone.now()
            log.filas_obtenidas = 0
            log.filas_creadas = 0
            log.filas_eliminadas = total_eliminados
            log.mensaje = (
                "Limpieza de registros antiguos completada correctamente. "
                f"RAW eliminados: {eliminados_raw}. "
                f"Limpio eliminados: {eliminados_limpio}."
            )
            log.save()

            self.stdout.write(
                self.style.SUCCESS(
                    "Limpieza de registros antiguos completada. "
                    f"RAW eliminados: {eliminados_raw} | "
                    f"Limpio eliminados: {eliminados_limpio}"
                )
            )

        except Exception as error:
            log.estado = "ERROR"
            log.fecha_fin = timezone.now()
            log.mensaje = f"Error limpiando registros antiguos: {error}"
            log.save()

            self.stderr.write(
                self.style.ERROR(f"Error limpiando registros antiguos: {error}")
            )