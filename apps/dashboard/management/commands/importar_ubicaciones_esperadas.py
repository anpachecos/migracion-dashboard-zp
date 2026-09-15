"""
Comando Django: importar_ubicaciones_esperadas.py

- Importa ubicaciones esperadas desde Excel de Zonas Pagas.
- Lee la hoja Version_DB.
- Guarda datos vigentes en Oracle: USR_LAB.UBICACION_ESPERADA_VALIDADOR.
- Guarda historial en Oracle: USR_LAB.HISTORIAL_UBICACION_ESPERADA.
- Si un AMID deja de venir en el Excel, lo mueve a Laboratorio Zonas Pagas.
- Extrae la versión desde el nombre del archivo, por ejemplo: ZONA PAGA V751 JUEVES.xlsx -> V751.
"""

from pathlib import Path
from datetime import datetime
import re
import unicodedata

import pandas as pd

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.repositories import ubicaciones_repository
from apps.dashboard.services.logs_service import registrar_log_importacion

LATITUD_LABORATORIO_ZP = -33.437191
LONGITUD_LABORATORIO_ZP = -70.656102
RADIO_LABORATORIO_ZP = 150
NOMBRE_LABORATORIO_ZP = "Laboratorio Zonas Pagas"


MAPEO_COLUMNAS_EXCEL = {
    "codigo zp ts": "CODIGO_ZP_TS",
    "cod parada1": "COD_PARADA1",
    "cod parada2": "COD_PARADA2",
    "nombre": "NOMBRE",
    "comuna": "COMUNA",
    "unidad": "UNIDAD",
    "operador": "OPERADOR",
    "un": "UN",
    "u n secundaria 1": "UN_SECUNDARIA_1",
    "u n secundaria 2": "UN_SECUNDARIA_2",
    "u n secundaria 3": "UN_SECUNDARIA_3",
    "pst": "PST",
    "servicios": "SERVICIOS",
    "total val vigentes por zp": "TOTAL_VAL_VIGENTES_ZP",
    "horario": "HORARIO",
    "horario laboral pm": "HORARIO_LABORAL_PM",
    "horario sabado": "HORARIO_SABADO",
    "horario domingo": "HORARIO_DOMINGO",
    "inicio operacion": "INICIO_OPERACION",
    "fin operacion": "FIN_OPERACION",
    "patente": "PATENTE",
    "op id": "OP_ID",
    "bus id": "BUS_ID",
    "serie val": "SERIE_VALIDADOR",
    "idds": "IDDS",
    "n val": "NUM_VAL",
    "latitud": "LATITUD_ESPERADA",
    "longitud": "LONGITUD_ESPERADA",
    "x": "X",
    "y": "Y",
    "operativa": "OPERATIVA",
    "contingencia": "CONTINGENCIA",
    "mixta": "MIXTA",
    "radio": "RADIO_METROS",
    "tipo": "TIPO",
    "renovada": "RENOVADA",
}


class Command(BaseCommand):
    help = "Importa ubicaciones esperadas de validadores desde Excel hacia Oracle."

    def add_arguments(self, parser):
        parser.add_argument(
            "ruta_excel",
            nargs="?",
            default=None,
            type=str,
            help="Ruta del archivo Excel de ubicaciones esperadas."
        )

    def handle(self, *args, **options):
        fecha_inicio_log = timezone.now()
        fecha_carga = self.ahora_oracle()
        ruta_excel = options["ruta_excel"]

        creados_vigente = 0
        actualizados_vigente = 0
        omitidos = 0
        nuevos_historial = 0
        cerrados_historial = 0
        sin_cambios_historial = 0
        movidos_laboratorio = 0
        filas_excel = 0

        if ruta_excel:
            ruta_excel = Path(ruta_excel)
        else:
            ruta_excel = Path(settings.BASE_DIR) / "VERSION ZONA PAGA.xlsx"

        if not ruta_excel.exists():
            mensaje = f"No se encontró el archivo: {ruta_excel}"

            registrar_log_importacion(
                origen="UBICACIONES_ORACLE",
                estado="ERROR",
                fecha_inicio=fecha_inicio_log,
                fecha_fin=timezone.now(),
                mensaje=mensaje,
            )

            self.stderr.write(
                self.style.ERROR(mensaje)
            )
            return

        archivo_origen = ruta_excel.name
        version_zp = self.extraer_version_desde_nombre(archivo_origen)

        self.stdout.write(f"Leyendo archivo: {ruta_excel}")
        self.stdout.write("Hoja utilizada: Version_DB")
        self.stdout.write(f"Versión detectada: {version_zp or 'Sin versión'}")

        try:
            df = pd.read_excel(ruta_excel, sheet_name="Version_DB")
        except ValueError:
            mensaje = "No se encontró la hoja Version_DB en el Excel."

            registrar_log_importacion(
                origen="UBICACIONES_ORACLE",
                estado="ERROR",
                fecha_inicio=fecha_inicio_log,
                fecha_fin=timezone.now(),
                mensaje=f"{mensaje} Archivo: {archivo_origen}",
            )

            self.stderr.write(
                self.style.ERROR(mensaje)
            )
            return
        except Exception as error:
            mensaje = f"Error leyendo Excel de ubicaciones: {error}"

            registrar_log_importacion(
                origen="UBICACIONES_ORACLE",
                estado="ERROR",
                fecha_inicio=fecha_inicio_log,
                fecha_fin=timezone.now(),
                mensaje=f"{mensaje}. Archivo: {archivo_origen}",
            )

            self.stderr.write(
                self.style.ERROR(mensaje)
            )
            return

        filas_excel = len(df)

        df = self.normalizar_dataframe(df)

        columnas_requeridas = [
            "IDDS",
            "NOMBRE",
            "SERIE_VALIDADOR",
            "LATITUD_ESPERADA",
            "LONGITUD_ESPERADA",
            "OPERATIVA",
            "RADIO_METROS",
        ]

        faltantes = [col for col in columnas_requeridas if col not in df.columns]

        if faltantes:
            mensaje = f"Faltan columnas requeridas en el Excel: {faltantes}"

            registrar_log_importacion(
                origen="UBICACIONES_ORACLE",
                estado="ERROR",
                fecha_inicio=fecha_inicio_log,
                fecha_fin=timezone.now(),
                filas_obtenidas=filas_excel,
                mensaje=f"{mensaje}. Archivo: {archivo_origen}",
            )

            self.stderr.write(
                self.style.ERROR(mensaje)
            )
            return

        estadisticas = {
            "creados_vigente": creados_vigente,
            "actualizados_vigente": actualizados_vigente,
            "omitidos": omitidos,
            "nuevos_historial": nuevos_historial,
            "cerrados_historial": cerrados_historial,
            "sin_cambios_historial": sin_cambios_historial,
            "movidos_laboratorio": movidos_laboratorio,
        }

        filas_normalizadas = (
            self.normalizar_fila(
                fila=fila,
                fecha_carga=fecha_carga,
                archivo_origen=archivo_origen,
                version_zp=version_zp,
            )
            for _, fila in df.iterrows()
        )

        referencia_laboratorio = {
            "NOMBRE": NOMBRE_LABORATORIO_ZP,
            "LATITUD_ESPERADA": LATITUD_LABORATORIO_ZP,
            "LONGITUD_ESPERADA": LONGITUD_LABORATORIO_ZP,
            "RADIO_METROS": RADIO_LABORATORIO_ZP,
            "OPERATIVA": 0,
            "ORIGEN_UBICACION": "laboratorio_default",
        }

        try:
            ubicaciones_repository.persistir_importacion(
                filas_normalizadas=filas_normalizadas,
                fecha_carga=fecha_carga,
                archivo_origen=archivo_origen,
                version_zp=version_zp,
                referencia_laboratorio=referencia_laboratorio,
                estadisticas=estadisticas,
            )

        except Exception as error:
            creados_vigente = estadisticas["creados_vigente"]
            movidos_laboratorio = estadisticas["movidos_laboratorio"]
            mensaje = f"Error importando ubicaciones a Oracle: {error}"

            registrar_log_importacion(
                origen="UBICACIONES_ORACLE",
                estado="ERROR",
                fecha_inicio=fecha_inicio_log,
                fecha_fin=timezone.now(),
                filas_obtenidas=filas_excel,
                filas_creadas=creados_vigente,
                filas_eliminadas=movidos_laboratorio,
                mensaje=mensaje,
            )

            self.stderr.write(
                self.style.ERROR(mensaje)
            )
            return

        creados_vigente = estadisticas["creados_vigente"]
        actualizados_vigente = estadisticas["actualizados_vigente"]
        omitidos = estadisticas["omitidos"]
        nuevos_historial = estadisticas["nuevos_historial"]
        cerrados_historial = estadisticas["cerrados_historial"]
        sin_cambios_historial = estadisticas["sin_cambios_historial"]
        movidos_laboratorio = estadisticas["movidos_laboratorio"]

        mensaje = (
            f"Importación completada en Oracle. "
            f"Archivo: {archivo_origen}. "
            f"Versión ZP: {version_zp or 'Sin versión'}. "
            f"Vigentes creados: {creados_vigente}. "
            f"Vigentes actualizados: {actualizados_vigente}. "
            f"Omitidos: {omitidos}. "
            f"Historial nuevos: {nuevos_historial}. "
            f"Historial cerrados: {cerrados_historial}. "
            f"Historial sin cambios: {sin_cambios_historial}. "
            f"Movidos a laboratorio: {movidos_laboratorio}."
        )

        registrar_log_importacion(
            origen="UBICACIONES_ORACLE",
            estado="OK",
            fecha_inicio=fecha_inicio_log,
            fecha_fin=timezone.now(),
            filas_obtenidas=filas_excel,
            filas_creadas=creados_vigente,
            filas_eliminadas=movidos_laboratorio,
            mensaje=mensaje,
        )

        self.stdout.write(self.style.SUCCESS("Importación completada en Oracle."))
        self.stdout.write(f"Fecha carga: {fecha_carga.strftime('%d-%m-%Y %H:%M:%S')}")
        self.stdout.write(f"Archivo origen: {archivo_origen}")
        self.stdout.write(f"Versión ZP: {version_zp or 'Sin versión'}")
        self.stdout.write(f"Filas Excel: {filas_excel}")
        self.stdout.write(f"Vigentes creados: {creados_vigente}")
        self.stdout.write(f"Vigentes actualizados: {actualizados_vigente}")
        self.stdout.write(f"Omitidos: {omitidos}")
        self.stdout.write(f"Historial nuevos: {nuevos_historial}")
        self.stdout.write(f"Historial cerrados: {cerrados_historial}")
        self.stdout.write(f"Historial sin cambios: {sin_cambios_historial}")
        self.stdout.write(f"Movidos a laboratorio por no venir en Excel: {movidos_laboratorio}")
    
    def ahora_oracle(self):
        ahora = timezone.localtime(timezone.now())

        if timezone.is_aware(ahora):
            return timezone.make_naive(ahora)

        return ahora

    def extraer_version_desde_nombre(self, nombre_archivo):
        coincidencia = re.search(r"\bV\s*([0-9]+)\b", nombre_archivo, flags=re.IGNORECASE)

        if coincidencia:
            return f"V{coincidencia.group(1)}"

        return None

    def normalizar_nombre_columna(self, valor):
        texto = str(valor).strip().lower()
        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        texto = re.sub(r"[^a-z0-9]+", " ", texto)
        texto = re.sub(r"\s+", " ", texto).strip()
        return texto

    def normalizar_dataframe(self, df):
        nuevas_columnas = {}

        for columna in df.columns:
            clave = self.normalizar_nombre_columna(columna)
            columna_oracle = MAPEO_COLUMNAS_EXCEL.get(clave)

            if columna_oracle:
                nuevas_columnas[columna] = columna_oracle

        df = df.rename(columns=nuevas_columnas)

        columnas_a_conservar = [
            columna for columna in ubicaciones_repository.COLUMNAS_ORACLE
            if columna not in ["AMID", "VERSION_ZP", "ARCHIVO_ORIGEN", "FECHA_CARGA"]
        ]

        for columna in columnas_a_conservar:
            if columna not in df.columns:
                df[columna] = None

        return df

    def normalizar_fila(self, fila, fecha_carga, archivo_origen, version_zp):
        amid = self.valor_amid(fila.get("IDDS"))

        if not amid:
            return None

        operativa_texto = self.texto(fila.get("OPERATIVA")).upper()

        if operativa_texto not in ["SI", "SÍ", "NO"]:
            return None

        datos = {
            "AMID": amid,
            "CODIGO_ZP_TS": self.texto_o_none(fila.get("CODIGO_ZP_TS")),
            "COD_PARADA1": self.texto_o_none(fila.get("COD_PARADA1")),
            "COD_PARADA2": self.texto_o_none(fila.get("COD_PARADA2")),
            "NOMBRE": self.texto_o_none(fila.get("NOMBRE")),
            "COMUNA": self.texto_o_none(fila.get("COMUNA")),
            "UNIDAD": self.texto_o_none(fila.get("UNIDAD")),
            "OPERADOR": self.texto_o_none(fila.get("OPERADOR")),
            "UN": self.texto_o_none(fila.get("UN")),
            "UN_SECUNDARIA_1": self.texto_o_none(fila.get("UN_SECUNDARIA_1")),
            "UN_SECUNDARIA_2": self.texto_o_none(fila.get("UN_SECUNDARIA_2")),
            "UN_SECUNDARIA_3": self.texto_o_none(fila.get("UN_SECUNDARIA_3")),
            "PST": self.texto_o_none(fila.get("PST")),
            "SERVICIOS": self.texto_o_none(fila.get("SERVICIOS")),
            "TOTAL_VAL_VIGENTES_ZP": self.valor_numero(fila.get("TOTAL_VAL_VIGENTES_ZP")),
            "HORARIO": self.texto_o_none(fila.get("HORARIO")),
            "HORARIO_LABORAL_PM": self.texto_o_none(fila.get("HORARIO_LABORAL_PM")),
            "HORARIO_SABADO": self.texto_o_none(fila.get("HORARIO_SABADO")),
            "HORARIO_DOMINGO": self.texto_o_none(fila.get("HORARIO_DOMINGO")),
            "INICIO_OPERACION": self.valor_fecha(fila.get("INICIO_OPERACION")),
            "FIN_OPERACION": self.valor_fecha(fila.get("FIN_OPERACION")),
            "PATENTE": self.texto_o_none(fila.get("PATENTE")),
            "OP_ID": self.valor_numero(fila.get("OP_ID")),
            "BUS_ID": self.valor_numero(fila.get("BUS_ID")),
            "SERIE_VALIDADOR": self.texto_o_none(fila.get("SERIE_VALIDADOR")),
            "IDDS": amid,
            "NUM_VAL": self.texto_o_none(fila.get("NUM_VAL")),
            "X": self.valor_numero(fila.get("X")),
            "Y": self.valor_numero(fila.get("Y")),
            "CONTINGENCIA": self.texto_o_none(fila.get("CONTINGENCIA")),
            "MIXTA": self.texto_o_none(fila.get("MIXTA")),
            "TIPO": self.texto_o_none(fila.get("TIPO")),
            "RENOVADA": self.texto_o_none(fila.get("RENOVADA")),
            "VERSION_ZP": version_zp,
            "ARCHIVO_ORIGEN": archivo_origen,
            "FECHA_CARGA": fecha_carga,
        }

        if operativa_texto in ["SI", "SÍ"]:
            latitud = self.valor_numero(fila.get("LATITUD_ESPERADA"))
            longitud = self.valor_numero(fila.get("LONGITUD_ESPERADA"))
            radio = self.valor_numero(fila.get("RADIO_METROS"))

            if latitud is None or longitud is None or radio is None:
                return None

            datos["LATITUD_ESPERADA"] = latitud
            datos["LONGITUD_ESPERADA"] = longitud
            datos["RADIO_METROS"] = radio
            datos["OPERATIVA"] = 1
            datos["ORIGEN_UBICACION"] = "excel"

        else:
            datos["NOMBRE"] = NOMBRE_LABORATORIO_ZP
            datos["LATITUD_ESPERADA"] = LATITUD_LABORATORIO_ZP
            datos["LONGITUD_ESPERADA"] = LONGITUD_LABORATORIO_ZP
            datos["RADIO_METROS"] = RADIO_LABORATORIO_ZP
            datos["OPERATIVA"] = 0
            datos["ORIGEN_UBICACION"] = "laboratorio"

        return datos

    def texto(self, valor):
        if valor is None:
            return ""

        if pd.isna(valor):
            return ""

        return str(valor).strip()

    def texto_o_none(self, valor):
        texto = self.texto(valor)

        if texto == "" or texto.lower() == "nan":
            return None

        return texto

    def valor_amid(self, valor):
        if valor is None or pd.isna(valor):
            return None

        try:
            return str(int(float(valor))).strip()
        except (ValueError, TypeError):
            texto = self.texto(valor)
            return texto if texto else None

    def valor_numero(self, valor):
        if valor is None or pd.isna(valor):
            return None

        try:
            return float(valor)
        except (ValueError, TypeError):
            texto = str(valor).strip().replace(",", ".")

            try:
                return float(texto)
            except (ValueError, TypeError):
                return None

    def valor_fecha(self, valor):
        if valor is None or pd.isna(valor):
            return None

        fecha = pd.to_datetime(valor, errors="coerce", dayfirst=True)

        if pd.isna(fecha):
            return None

        fecha_python = fecha.to_pydatetime()

        if timezone.is_aware(fecha_python):
            fecha_python = timezone.make_naive(fecha_python)

        return fecha_python
