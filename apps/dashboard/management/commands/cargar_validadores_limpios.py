from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.models import (
    EstadoValidadorRaw,
    EstadoValidadorLimpio,
    LogImportacion,
)


class Command(BaseCommand):
    help = "Carga datos desde EstadoValidadorRaw hacia EstadoValidadorLimpio"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reprocesar",
            action="store_true",
            help="Reprocesa todos los registros RAW de las últimas dos semanas.",
        )

    def handle(self, *args, **options):
        fecha_inicio = timezone.now()

        log = LogImportacion.objects.create(
            origen="LIMPIEZA",
            estado="OK",
            fecha_inicio=fecha_inicio,
            mensaje="Carga de datos limpios iniciada",
        )

        try:
            limite = timezone.now() - timedelta(days=14)

            queryset_raw = EstadoValidadorRaw.objects.filter(
                fecha_hora__gte=limite
            ).order_by("fecha_hora")

            if not options["reprocesar"]:
                ultimo_log_limpieza = (
                    LogImportacion.objects
                    .filter(
                        origen="LIMPIEZA",
                        estado="OK",
                        fecha_fin__isnull=False,
                    )
                    .exclude(id=log.id)
                    .order_by("-fecha_fin")
                    .first()
                )

                if ultimo_log_limpieza:
                    queryset_raw = queryset_raw.filter(
                        fecha_importacion__gt=ultimo_log_limpieza.fecha_inicio
                    )

            total_raw = queryset_raw.count()

            self.stdout.write(f"Registros RAW a cargar en Limpio: {total_raw}")

            registros_limpios = []

            for raw in queryset_raw.iterator(chunk_size=1000):
                limpio = EstadoValidadorLimpio(
                    amid=raw.amid,
                    fec_descarga=raw.fec_descarga,
                    fec_estado=raw.fec_estado,
                    busid=raw.busid,
                    op=raw.op,
                    version=raw.version,
                    patente=raw.patente,
                    td01=raw.td01,
                    td04=raw.td04,
                    tabla=raw.tabla,
                    ver_tabla=raw.ver_tabla,
                    fecha_hora=raw.fecha_hora,
                    is_contiene_bateria=raw.is_contiene_bateria,
                    is_contiene_gps=raw.is_contiene_gps,
                    is_contiene_tiempo_vida=raw.is_contiene_tiempo_vida,
                    is_error_obtener_bateria=raw.is_error_obtener_bateria,
                    is_error_obtener_gps=raw.is_error_obtener_gps,
                    is_error_obtener_tiempo_vida=raw.is_error_obtener_tiempo_vida,
                    latitud=raw.latitud,
                    longitud=raw.longitud,
                    porcentaje_bateria=raw.porcentaje_bateria,
                    tiempo_vida=raw.tiempo_vida,
                    fecha_registro=raw.fecha_registro,
                    fecha_importacion=raw.fecha_importacion,
                )

                registros_limpios.append(limpio)

            cantidad_antes = EstadoValidadorLimpio.objects.count()

            EstadoValidadorLimpio.objects.bulk_create(
                registros_limpios,
                batch_size=500,
                ignore_conflicts=True,
            )

            cantidad_despues = EstadoValidadorLimpio.objects.count()

            filas_creadas = cantidad_despues - cantidad_antes
            duplicados_ignorados = len(registros_limpios) - filas_creadas

            log.estado = "OK"
            log.fecha_fin = timezone.now()
            log.filas_obtenidas = total_raw
            log.filas_creadas = filas_creadas
            log.filas_eliminadas = 0
            log.mensaje = (
                "Carga de datos limpios completada correctamente. "
                f"Duplicados ignorados: {duplicados_ignorados}"
            )
            log.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Carga a Limpio completada. "
                    f"RAW procesados: {total_raw} | "
                    f"Limpios creados: {filas_creadas} | "
                    f"Duplicados ignorados: {duplicados_ignorados}"
                )
            )

        except Exception as error:
            log.estado = "ERROR"
            log.fecha_fin = timezone.now()
            log.mensaje = f"Error cargando datos limpios: {error}"
            log.save()

            self.stderr.write(
                self.style.ERROR(f"Error cargando datos limpios: {error}")
            )