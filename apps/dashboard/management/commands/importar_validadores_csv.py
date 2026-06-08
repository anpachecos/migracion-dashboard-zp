"""
Comando Django: importar_validadores_csv.py
- Importa datos de validadores desde un archivo CSV hacia el modelo EstadoValidador.
- Usa datos_query_prueba.csv por defecto, o un archivo especificado con --archivo.
- Opción --limpiar elimina los registros existentes antes de importar.
- Convierte columnas a enteros, decimales, booleanos y fechas.
"""
import pandas as pd
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from apps.dashboard.models import EstadoValidador


class Command(BaseCommand):
    help = "Importa datos de validadores desde datos_query_prueba.csv hacia SQLite"

    def add_arguments(self, parser):
        parser.add_argument(
            "--archivo",
            type=str,
            default="datos_query_prueba.csv",
            help="Ruta del archivo CSV a importar. Por defecto: datos_query_prueba.csv",
        )

        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Elimina los datos existentes antes de importar.",
        )

    def handle(self, *args, **options):
        archivo = Path(settings.BASE_DIR) / options["archivo"]

        if not archivo.exists():
            self.stderr.write(self.style.ERROR(f"No se encontró el archivo: {archivo}"))
            return

        if options["limpiar"]:
            total_eliminados, _ = EstadoValidador.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"Registros eliminados: {total_eliminados}")
            )

        df = pd.read_csv(archivo)

        self.stdout.write(f"Archivo leído correctamente: {archivo}")
        self.stdout.write(f"Filas encontradas en CSV: {len(df)}")

        registros = []

        for _, fila in df.iterrows():
            registro = EstadoValidador(
                amid=self.valor_entero(fila.get("AMID")),

                fec_descarga=self.valor_fecha(fila.get("FEC_DESCARGA"), dayfirst=True),
                fec_estado=self.valor_fecha(fila.get("FEC_ESTADO"), dayfirst=True),

                busid=self.valor_entero(fila.get("BUSID")),
                op=self.valor_entero(fila.get("OP")),

                version=self.valor_texto(fila.get("VERSION")),
                patente=self.valor_texto(fila.get("PATENTE")),

                td01=self.valor_entero(fila.get("TD01")),
                td04=self.valor_entero(fila.get("TD04")),

                tabla=self.valor_entero(fila.get("TABLA")),
                ver_tabla=self.valor_texto(fila.get("VER_TABLA")),
                fecha_hora=self.valor_fecha(fila.get("FECHA_HORA"), dayfirst=True),

                is_contiene_bateria=self.valor_booleano(fila.get("IS_CONTIENE_BATERIA")),
                is_contiene_gps=self.valor_booleano(fila.get("IS_CONTIENE_GPS")),
                is_contiene_tiempo_vida=self.valor_booleano(fila.get("IS_CONTIENE_TIEMPO_VIDA")),

                is_error_obtener_bateria=self.valor_booleano(fila.get("IS_ERROR_OBTENER_BATERIA")),
                is_error_obtener_gps=self.valor_booleano(fila.get("IS_ERROR_OBTENER_GPS")),
                is_error_obtener_tiempo_vida=self.valor_booleano(fila.get("IS_ERROR_OBTENER_TIEMPO_VIDA")),

                latitud=self.valor_decimal(fila.get("LATITUD")),
                longitud=self.valor_decimal(fila.get("LONGITUD")),
                porcentaje_bateria=self.valor_entero(fila.get("PORCENTAJE_BATERIA")),

                tiempo_vida=self.valor_fecha(fila.get("TIEMPO_VIDA")),
                fecha_registro=self.valor_fecha(fila.get("FECHA_REGISTRO")),
            )

            registros.append(registro)

        EstadoValidador.objects.bulk_create(registros, batch_size=500)

        self.stdout.write(
            self.style.SUCCESS(f"Importación completada. Registros creados: {len(registros)}")
        )

    def valor_texto(self, valor):
        if pd.isna(valor):
            return None

        texto = str(valor).strip()

        if texto == "":
            return None

        return texto

    def valor_entero(self, valor):
        if pd.isna(valor):
            return None

        try:
            return int(float(valor))
        except (ValueError, TypeError):
            return None

    def valor_decimal(self, valor):
        if pd.isna(valor):
            return None

        try:
            return Decimal(str(valor).strip())
        except (InvalidOperation, ValueError, TypeError):
            return None

    def valor_booleano(self, valor):
        if pd.isna(valor):
            return None

        texto = str(valor).strip().lower()

        if texto in ["true", "1", "si", "sí", "yes"]:
            return True

        if texto in ["false", "0", "no"]:
            return False

        return None

    def valor_fecha(self, valor, dayfirst=False):
        if pd.isna(valor):
            return None

        try:
            fecha = pd.to_datetime(valor, dayfirst=dayfirst, errors="coerce")

            if pd.isna(fecha):
                return None

            fecha_python = fecha.to_pydatetime()

            if timezone.is_naive(fecha_python):
                fecha_python = timezone.make_aware(fecha_python)

            return fecha_python

        except Exception:
            return None