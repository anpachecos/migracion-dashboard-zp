from django.core.management.base import BaseCommand
from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


class Command(BaseCommand):
    help = "Prueba la conexión a Oracle"

    def handle(self, *args, **options):
        try:
            with obtener_conexion_oracle() as conexion:
                with conexion.cursor() as cursor:
                    cursor.execute("SELECT SYSDATE FROM dual")
                    resultado = cursor.fetchone()

            self.stdout.write(
                self.style.SUCCESS(f"Conexión Oracle OK. SYSDATE: {resultado[0]}")
            )

        except Exception as error:
            self.stderr.write(
                self.style.ERROR(f"Error conectando a Oracle: {error}")
            )   