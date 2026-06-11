"""
Comando Django: importar_ubicaciones_esperadas.py

- Importa ubicaciones esperadas de validadores desde un archivo Excel de Zonas Pagas.
- Lee únicamente la hoja Version_DB.
- Actualiza la tabla vigente UbicacionEsperadaValidador.
- Guarda historial de cambios en HistorialUbicacionEsperadaValidador.
- Si un validador deja de venir en el Excel, lo mueve a Laboratorio Zonas Pagas.
"""

from pathlib import Path

import pandas as pd

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.models import (
    UbicacionEsperadaValidador,
    HistorialUbicacionEsperadaValidador,
)


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
        fecha_carga = timezone.now()
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
        self.stdout.write("Hoja utilizada: Version_DB")

        try:
            df = pd.read_excel(ruta_excel, sheet_name="Version_DB")
        except ValueError:
            self.stderr.write(
                self.style.ERROR("No se encontró la hoja Version_DB en el Excel.")
            )
            return

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

        creados_vigente = 0
        actualizados_vigente = 0
        omitidos = 0
        nuevos_historial = 0
        cerrados_historial = 0
        sin_cambios_historial = 0

        amids_excel = set()

        for _, fila in df.iterrows():
            datos = self.normalizar_fila(fila)

            if datos is None:
                omitidos += 1
                continue

            amid = datos["amid"]
            amids_excel.add(amid)

            objeto, creado = UbicacionEsperadaValidador.objects.update_or_create(
                amid=amid,
                defaults={
                    "nombre": datos["nombre"],
                    "serie_validador": datos["serie_validador"],
                    "latitud_esperada": datos["latitud_esperada"],
                    "longitud_esperada": datos["longitud_esperada"],
                    "radio_metros": datos["radio_metros"],
                    "operativa": datos["operativa"],
                    "fecha_carga": fecha_carga,
                }
            )

            if creado:
                creados_vigente += 1
            else:
                actualizados_vigente += 1

            resultado_historial = self.actualizar_historial(
                datos=datos,
                fecha_carga=fecha_carga,
                archivo_origen=ruta_excel.name,
            )

            if resultado_historial == "nuevo":
                nuevos_historial += 1
            elif resultado_historial == "cerrado_y_nuevo":
                cerrados_historial += 1
                nuevos_historial += 1
            elif resultado_historial == "sin_cambios":
                sin_cambios_historial += 1

        movidos_laboratorio, cerrados_por_ausencia, historicos_por_ausencia = (
            self.mover_ausentes_a_laboratorio(
                amids_excel=amids_excel,
                fecha_carga=fecha_carga,
                archivo_origen=ruta_excel.name,
            )
        )

        cerrados_historial += cerrados_por_ausencia
        nuevos_historial += historicos_por_ausencia

        self.stdout.write(self.style.SUCCESS("Importación completada."))
        self.stdout.write(f"Fecha carga: {timezone.localtime(fecha_carga).strftime('%d-%m-%Y %H:%M:%S')}")
        self.stdout.write(f"Vigentes creados: {creados_vigente}")
        self.stdout.write(f"Vigentes actualizados: {actualizados_vigente}")
        self.stdout.write(f"Omitidos: {omitidos}")
        self.stdout.write(f"Historial nuevos: {nuevos_historial}")
        self.stdout.write(f"Historial cerrados: {cerrados_historial}")
        self.stdout.write(f"Historial sin cambios: {sin_cambios_historial}")
        self.stdout.write(f"Movidos a laboratorio por no venir en Excel: {movidos_laboratorio}")

    def normalizar_fila(self, fila):
        operativa_texto = str(fila["Operativa"]).strip().upper()

        if operativa_texto not in ["SI", "NO"]:
            return None

        try:
            amid = str(int(fila["IDDS"])).strip()
        except (ValueError, TypeError):
            return None

        serie_validador = (
            str(fila["Serie Val."]).strip()
            if pd.notna(fila["Serie Val."])
            else ""
        )

        if operativa_texto == "SI":
            try:
                latitud = float(fila["Latitud"])
                longitud = float(fila["Longitud"])
                radio = float(fila["Radio"])
            except (ValueError, TypeError):
                return None

            nombre = (
                str(fila["Nombre"]).strip()
                if pd.notna(fila["Nombre"])
                else ""
            )
            operativa = True
            origen_ubicacion = "excel"

        else:
            latitud = LATITUD_LABORATORIO_ZP
            longitud = LONGITUD_LABORATORIO_ZP
            radio = RADIO_LABORATORIO_ZP
            nombre = NOMBRE_LABORATORIO_ZP
            operativa = False
            origen_ubicacion = "laboratorio"

        return {
            "amid": amid,
            "nombre": nombre,
            "serie_validador": serie_validador,
            "latitud_esperada": latitud,
            "longitud_esperada": longitud,
            "radio_metros": radio,
            "operativa": operativa,
            "origen_ubicacion": origen_ubicacion,
        }

    def actualizar_historial(self, datos, fecha_carga, archivo_origen):
        historial_vigente = (
            HistorialUbicacionEsperadaValidador.objects
            .filter(
                amid=datos["amid"],
                fecha_fin_vigencia__isnull=True,
            )
            .order_by("-fecha_inicio_vigencia")
            .first()
        )

        if historial_vigente is None:
            self.crear_historial(datos, fecha_carga, archivo_origen)
            return "nuevo"

        if self.historial_es_igual(historial_vigente, datos):
            return "sin_cambios"

        historial_vigente.fecha_fin_vigencia = fecha_carga
        historial_vigente.save(update_fields=["fecha_fin_vigencia"])

        self.crear_historial(datos, fecha_carga, archivo_origen)

        return "cerrado_y_nuevo"

    def crear_historial(self, datos, fecha_carga, archivo_origen):
        HistorialUbicacionEsperadaValidador.objects.create(
            amid=datos["amid"],
            nombre=datos["nombre"],
            serie_validador=datos["serie_validador"],
            latitud_esperada=datos["latitud_esperada"],
            longitud_esperada=datos["longitud_esperada"],
            radio_metros=datos["radio_metros"],
            operativa=datos["operativa"],
            origen_ubicacion=datos["origen_ubicacion"],
            fecha_inicio_vigencia=fecha_carga,
            fecha_fin_vigencia=None,
            fecha_carga=fecha_carga,
            archivo_origen=archivo_origen,
        )

    def historial_es_igual(self, historial, datos):
        return (
            self.texto(historial.nombre) == self.texto(datos["nombre"])
            and self.texto(historial.serie_validador) == self.texto(datos["serie_validador"])
            and self.numero_igual(historial.latitud_esperada, datos["latitud_esperada"])
            and self.numero_igual(historial.longitud_esperada, datos["longitud_esperada"])
            and self.numero_igual(historial.radio_metros, datos["radio_metros"])
            and historial.operativa == datos["operativa"]
            and self.texto(historial.origen_ubicacion) == self.texto(datos["origen_ubicacion"])
        )

    def mover_ausentes_a_laboratorio(self, amids_excel, fecha_carga, archivo_origen):
        movidos = 0
        cerrados_historial = 0
        nuevos_historial = 0

        ubicaciones_ausentes = (
            UbicacionEsperadaValidador.objects
            .exclude(amid__in=amids_excel)
        )

        for ubicacion in ubicaciones_ausentes:
            datos_laboratorio = {
                "amid": ubicacion.amid,
                "nombre": NOMBRE_LABORATORIO_ZP,
                "serie_validador": ubicacion.serie_validador or "",
                "latitud_esperada": LATITUD_LABORATORIO_ZP,
                "longitud_esperada": LONGITUD_LABORATORIO_ZP,
                "radio_metros": RADIO_LABORATORIO_ZP,
                "operativa": False,
                "origen_ubicacion": "laboratorio_default",
            }

            ya_esta_en_laboratorio = (
                self.texto(ubicacion.nombre) == self.texto(NOMBRE_LABORATORIO_ZP)
                and self.numero_igual(ubicacion.latitud_esperada, LATITUD_LABORATORIO_ZP)
                and self.numero_igual(ubicacion.longitud_esperada, LONGITUD_LABORATORIO_ZP)
                and self.numero_igual(ubicacion.radio_metros, RADIO_LABORATORIO_ZP)
                and ubicacion.operativa is False
            )

            if ya_esta_en_laboratorio:
                continue

            ubicacion.nombre = NOMBRE_LABORATORIO_ZP
            ubicacion.latitud_esperada = LATITUD_LABORATORIO_ZP
            ubicacion.longitud_esperada = LONGITUD_LABORATORIO_ZP
            ubicacion.radio_metros = RADIO_LABORATORIO_ZP
            ubicacion.operativa = False
            ubicacion.fecha_carga = fecha_carga
            ubicacion.save()

            historial_vigente = (
                HistorialUbicacionEsperadaValidador.objects
                .filter(
                    amid=ubicacion.amid,
                    fecha_fin_vigencia__isnull=True,
                )
                .order_by("-fecha_inicio_vigencia")
                .first()
            )

            if historial_vigente:
                historial_vigente.fecha_fin_vigencia = fecha_carga
                historial_vigente.save(update_fields=["fecha_fin_vigencia"])
                cerrados_historial += 1

            HistorialUbicacionEsperadaValidador.objects.create(
                amid=ubicacion.amid,
                nombre=NOMBRE_LABORATORIO_ZP,
                serie_validador=ubicacion.serie_validador or "",
                latitud_esperada=LATITUD_LABORATORIO_ZP,
                longitud_esperada=LONGITUD_LABORATORIO_ZP,
                radio_metros=RADIO_LABORATORIO_ZP,
                operativa=False,
                origen_ubicacion="laboratorio_default",
                fecha_inicio_vigencia=fecha_carga,
                fecha_fin_vigencia=None,
                fecha_carga=fecha_carga,
                archivo_origen=archivo_origen,
            )

            nuevos_historial += 1
            movidos += 1

        return movidos, cerrados_historial, nuevos_historial


    def texto(self, valor):
        if valor is None:
            return ""

        return str(valor).strip()

    def numero_igual(self, valor_1, valor_2):
        if valor_1 is None and valor_2 is None:
            return True

        if valor_1 is None or valor_2 is None:
            return False

        try:
            return round(float(valor_1), 7) == round(float(valor_2), 7)
        except (ValueError, TypeError):
            return False