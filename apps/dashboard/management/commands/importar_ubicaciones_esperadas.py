from pathlib import Path

import pandas as pd

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.models import UbicacionEsperadaValidador

LATITUD_LABORATORIO_ZP = -33.437191
LONGITUD_LABORATORIO_ZP = -70.656102
RADIO_LABORATORIO_ZP = 150
NOMBRE_LABORATORIO_ZP = "Laboratorio Zonas Pagas"

class Command(BaseCommand):
    help = "Importa ubicaciones esperadas de validadores desde Excel de Zonas Pagas."

    def add_arguments(self, parser):
        parser.add_argument(
            "ruta_excel",
            nargs="?",
            default=None,
            type=str,
            help="Ruta del archivo Excel de ubicaciones esperadas."
        )

    def handle(self, *args, **options):
        ruta_excel = options["ruta_excel"]

        if ruta_excel:
            ruta_excel = Path(ruta_excel)
        else:
            ruta_excel = Path(settings.BASE_DIR) / "VERSION ZONA PAGA.xlsx"

        if not ruta_excel.exists():
            self.stderr.write(
                self.style.ERROR(f"No se encontró el archivo: {ruta_excel}")
            )
            return

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


        creados = 0
        actualizados = 0
        omitidos = 0

        amids_excel = set()

        for _, fila in df.iterrows():
            operativa_texto = str(fila["Operativa"]).strip().upper()
            if operativa_texto not in ["SI", "NO"]:
                omitidos += 1
                continue

            try:
                amid = str(int(fila["IDDS"])).strip()
            except (ValueError, TypeError):
                omitidos += 1
                continue

            serie_validador = str(fila["Serie Val."]).strip() if pd.notna(fila["Serie Val."]) else ""

            if operativa_texto == "SI":
                try:
                    latitud = float(fila["Latitud"])
                    longitud = float(fila["Longitud"])
                    radio = float(fila["Radio"])
                except (ValueError, TypeError):
                    omitidos += 1
                    continue

                nombre = str(fila["Nombre"]).strip() if pd.notna(fila["Nombre"]) else ""
                operativa = True

            else:
                latitud = LATITUD_LABORATORIO_ZP
                longitud = LONGITUD_LABORATORIO_ZP
                radio = RADIO_LABORATORIO_ZP
                nombre = NOMBRE_LABORATORIO_ZP
                operativa = False

            objeto, creado = UbicacionEsperadaValidador.objects.update_or_create(
                amid=amid,
                defaults={
                    "nombre": nombre,
                    "serie_validador": serie_validador,
                    "latitud_esperada": latitud,
                    "longitud_esperada": longitud,
                    "radio_metros": radio,
                    "operativa": operativa,
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