from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.services.logs_service import registrar_log_importacion
from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


class Command(BaseCommand):
    help = "Limpia historial cerrado antiguo de ubicaciones esperadas en Oracle."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias-retencion",
            type=int,
            default=16,
            help="Días de retención para historial cerrado. Default: 16.",
        )

    def handle(self, *args, **options):
        dias_retencion = options["dias_retencion"]
        fecha_inicio = timezone.now()

        if dias_retencion < 1:
            mensaje = "Los días de retención deben ser mayores o iguales a 1."

            registrar_log_importacion(
                origen="UBICACIONES_ORACLE",
                estado="ERROR",
                fecha_inicio=fecha_inicio,
                fecha_fin=timezone.now(),
                mensaje=mensaje,
            )

            self.stderr.write(self.style.ERROR(mensaje))
            return

        try:
            with obtener_conexion_oracle() as conexion:
                with conexion.cursor() as cursor:
                    filas_eliminadas_var = cursor.var(int)

                    cursor.callproc(
                        "USR_LAB.PRC_LIMPIAR_HIST_UBICACION",
                        [
                            dias_retencion,
                            filas_eliminadas_var,
                        ],
                    )

                    filas_eliminadas = filas_eliminadas_var.getvalue() or 0

            mensaje = (
                "Limpieza de historial de ubicaciones Oracle ejecutada correctamente. "
                f"Retención: {dias_retencion} días. "
                f"Filas eliminadas: {filas_eliminadas}."
            )

            registrar_log_importacion(
                origen="UBICACIONES_ORACLE",
                estado="OK",
                fecha_inicio=fecha_inicio,
                fecha_fin=timezone.now(),
                filas_obtenidas=0,
                filas_creadas=0,
                filas_eliminadas=filas_eliminadas,
                mensaje=mensaje,
            )

            self.stdout.write(self.style.SUCCESS(mensaje))

        except Exception as error:
            mensaje = f"Error limpiando historial de ubicaciones Oracle: {error}"

            registrar_log_importacion(
                origen="UBICACIONES_ORACLE",
                estado="ERROR",
                fecha_inicio=fecha_inicio,
                fecha_fin=timezone.now(),
                mensaje=mensaje,
            )

            self.stderr.write(self.style.ERROR(mensaje))