"""
Comando Django: probar_oracle.py

- Prueba la conexión a la base de datos Oracle mediante una consulta simple.
- Ejecuta SELECT SYSDATE FROM dual para verificar que la conexión funciona.
- Registra el resultado en SQLite usando LogImportacion.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle
from apps.dashboard.services.logs_service import registrar_log_importacion


class Command(BaseCommand):
    help = "Prueba la conexión a Oracle y registra el resultado en logs internos."

    def handle(self, *args, **options):
        fecha_inicio = timezone.now()

        try:
            with obtener_conexion_oracle() as conexion:
                with conexion.cursor() as cursor:
                    cursor.execute("SELECT SYSDATE FROM dual")
                    resultado = cursor.fetchone()

            fecha_fin = timezone.now()

            mensaje = f"Conexión Oracle OK. SYSDATE: {resultado[0]}"

            registrar_log_importacion(
                origen="PROBAR_ORACLE",
                estado="OK",
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                filas_obtenidas=1,
                filas_creadas=0,
                filas_eliminadas=0,
                mensaje=mensaje,
            )

            self.stdout.write(
                self.style.SUCCESS(mensaje)
            )

        except Exception as error:
            fecha_fin = timezone.now()
            mensaje = f"Error conectando a Oracle: {error}"

            registrar_log_importacion(
                origen="PROBAR_ORACLE",
                estado="ERROR",
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                filas_obtenidas=0,
                filas_creadas=0,
                filas_eliminadas=0,
                mensaje=mensaje,
            )

            self.stderr.write(
                self.style.ERROR(mensaje)
            )