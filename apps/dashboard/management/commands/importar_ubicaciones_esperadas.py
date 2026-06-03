import pandas as pd

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.models import UbicacionEsperadaValidador


class Command(BaseCommand):
    help = "Importa ubicaciones esperadas de validadores desde Excel de Zonas Pagas."

    def add_arguments(self, parser):
        parser.add_argument(
            "ruta_excel",
            type=str,
            help="Ruta del archivo Excel de ubicaciones esperadas."
        )

    def handle(self, *args, **options):
        ruta_excel = options["ruta_excel"]

        self.stdout.write(f"Leyendo archivo: {ruta_excel}")

        df = pd.read_excel(ruta_excel, sheet_name="Version_DB")

        columnas_requeridas = [
            "IDDS",
            "Nombre",
            "Serie Val.",
            "Latitud",
            "Longitud",
            "Operativa",
            "Radio",
        ]

        faltantes = [col for col in columnas_requeridas if col not in df.columns]

        if faltantes:
            self.stderr.write(
                self.style.ERROR(f"Faltan columnas requeridas: {faltantes}")
            )
            return

        df = df[df["Operativa"].astype(str).str.upper().str.strip() == "SI"]

        creados = 0
        actualizados = 0
        omitidos = 0

        amids_excel = set()

        for _, fila in df.iterrows():
            try:
                amid = str(int(fila["IDDS"])).strip()
            except (ValueError, TypeError):
                omitidos += 1
                continue

            try:
                latitud = float(fila["Latitud"])
                longitud = float(fila["Longitud"])
                radio = float(fila["Radio"])
            except (ValueError, TypeError):
                omitidos += 1
                continue

            nombre = str(fila["Nombre"]).strip() if pd.notna(fila["Nombre"]) else ""
            serie_validador = str(fila["Serie Val."]).strip() if pd.notna(fila["Serie Val."]) else ""

            objeto, creado = UbicacionEsperadaValidador.objects.update_or_create(
                amid=amid,
                defaults={
                    "nombre": nombre,
                    "serie_validador": serie_validador,
                    "latitud_esperada": latitud,
                    "longitud_esperada": longitud,
                    "radio_metros": radio,
                    "operativa": True,
                    "fecha_carga": timezone.now(),
                }
            )

            amids_excel.add(amid)

            if creado:
                creados += 1
            else:
                actualizados += 1

        # Opcional pero recomendable:
        # Todo AMID que ya estaba en SQLite pero no viene operativo en el Excel actual,
        # queda marcado como no operativo.
        desactivados = (
            UbicacionEsperadaValidador.objects
            .exclude(amid__in=amids_excel)
            .update(operativa=False)
        )

        self.stdout.write(self.style.SUCCESS("Importación completada."))
        self.stdout.write(f"Creados: {creados}")
        self.stdout.write(f"Actualizados: {actualizados}")
        self.stdout.write(f"Omitidos: {omitidos}")
        self.stdout.write(f"Marcados no operativos: {desactivados}")