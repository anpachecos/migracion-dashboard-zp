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

import pandas as pd

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.dashboard.repositories import ubicaciones_repository
from apps.dashboard.services.gps_service import (
    LATITUD_LABORATORIO_ZP,
    LONGITUD_LABORATORIO_ZP,
    NOMBRE_LABORATORIO_ZP,
    RADIO_LABORATORIO_ZP,
)
from apps.dashboard.services.logs_service import registrar_log_importacion
from apps.dashboard.importacion.utilidades_pandas import texto
from apps.dashboard.importacion.ubicaciones_dataset_validation import (
    CAMPO_FILA_ORIGEN,
    formatear_reporte_validacion,
    resumir_incidencias,
    validar_dataset_ubicaciones,
)
from apps.dashboard.importacion.version_zp import (
    VERSION_ZP_SHEET_NAME,
    nombre_columna_oracle,
    normalizar_nombre_columna,
)
from apps.dashboard.importacion.version_zp_validation import (
    VersionZPValidationError,
    validar_archivo_version_zp,
)


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
            raise CommandError(mensaje)

        archivo_origen = ruta_excel.name
        version_zp = self.extraer_version_desde_nombre(archivo_origen)

        self.stdout.write(f"Leyendo archivo: {ruta_excel}")
        self.stdout.write(f"Hoja utilizada: {VERSION_ZP_SHEET_NAME}")
        self.stdout.write(f"Versión detectada: {version_zp or 'Sin versión'}")

        try:
            validar_archivo_version_zp(ruta_excel)
        except VersionZPValidationError as error:
            mensaje = str(error)

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
            raise CommandError(mensaje) from error

        try:
            df = pd.read_excel(ruta_excel, sheet_name=VERSION_ZP_SHEET_NAME)
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
            raise CommandError(mensaje) from error

        filas_excel = len(df)

        df = self.normalizar_dataframe(df)

        estadisticas = {
            "creados_vigente": creados_vigente,
            "actualizados_vigente": actualizados_vigente,
            "omitidos": omitidos,
            "nuevos_historial": nuevos_historial,
            "cerrados_historial": cerrados_historial,
            "sin_cambios_historial": sin_cambios_historial,
            "movidos_laboratorio": movidos_laboratorio,
        }

        referencia_laboratorio = {
            "NOMBRE": NOMBRE_LABORATORIO_ZP,
            "LATITUD_ESPERADA": LATITUD_LABORATORIO_ZP,
            "LONGITUD_ESPERADA": LONGITUD_LABORATORIO_ZP,
            "RADIO_METROS": RADIO_LABORATORIO_ZP,
            "OPERATIVA": 0,
            "ORIGEN_UBICACION": "laboratorio_default",
        }

        filas_neutrales = [
            self.adaptar_fila_dataframe(
                fila=fila,
                fila_excel=numero_fila,
                fecha_carga=fecha_carga,
                archivo_origen=archivo_origen,
                version_zp=version_zp,
            )
            for numero_fila, (_, fila) in enumerate(df.iterrows(), start=2)
        ]
        resultado_validacion = validar_dataset_ubicaciones(
            filas_neutrales,
            referencia_laboratorio,
        )

        if not resultado_validacion.es_valido:
            reporte = formatear_reporte_validacion(resultado_validacion)
            registrar_log_importacion(
                origen="UBICACIONES_ORACLE",
                estado="ERROR",
                fecha_inicio=fecha_inicio_log,
                fecha_fin=timezone.now(),
                filas_obtenidas=filas_excel,
                mensaje=(
                    f"Archivo: {archivo_origen}. "
                    f"Filas con error: {resultado_validacion.total_filas_con_error}. "
                    f"Incidencias: {len(resultado_validacion.incidencias)}.\n{reporte}"
                ),
            )
            self.stderr.write(self.style.ERROR(reporte))
            error_comando = CommandError(
                "No se importó Version_DB: "
                f"{resumir_incidencias(resultado_validacion)}. "
                "Oracle no fue modificado."
            )
            error_comando.detalle_usuario = reporte
            raise error_comando

        filas_normalizadas = list(resultado_validacion.registros)
        amids_presentes = set(resultado_validacion.amids_presentes)

        try:
            ubicaciones_repository.persistir_importacion(
                filas_normalizadas=filas_normalizadas,
                amids_presentes=amids_presentes,
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
            raise CommandError(mensaje) from error

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
        return normalizar_nombre_columna(valor)

    def normalizar_dataframe(self, df):
        nuevas_columnas = {}

        for columna in df.columns:
            columna_oracle = nombre_columna_oracle(columna)

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

    def adaptar_fila_dataframe(
        self,
        fila,
        fila_excel,
        fecha_carga,
        archivo_origen,
        version_zp,
    ):
        datos = {
            CAMPO_FILA_ORIGEN: fila_excel,
            "CODIGO_ZP_TS": self.texto_o_none(fila.get("CODIGO_ZP_TS")),
            "COD_PARADA1": self.texto_o_none(fila.get("COD_PARADA1")),
            "COD_PARADA2": self.texto_o_none(fila.get("COD_PARADA2")),
            "NOMBRE": self.valor_python(fila.get("NOMBRE")),
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
            "SERIE_VALIDADOR": self.valor_python(fila.get("SERIE_VALIDADOR")),
            "IDDS": self.valor_python(fila.get("IDDS")),
            "NUM_VAL": self.texto_o_none(fila.get("NUM_VAL")),
            "X": self.valor_numero(fila.get("X")),
            "Y": self.valor_numero(fila.get("Y")),
            "LATITUD_ESPERADA": self.valor_python(fila.get("LATITUD_ESPERADA")),
            "LONGITUD_ESPERADA": self.valor_python(fila.get("LONGITUD_ESPERADA")),
            "OPERATIVA": self.valor_python(fila.get("OPERATIVA")),
            "CONTINGENCIA": self.texto_o_none(fila.get("CONTINGENCIA")),
            "MIXTA": self.texto_o_none(fila.get("MIXTA")),
            "RADIO_METROS": self.valor_python(fila.get("RADIO_METROS")),
            "TIPO": self.texto_o_none(fila.get("TIPO")),
            "RENOVADA": self.texto_o_none(fila.get("RENOVADA")),
            "VERSION_ZP": version_zp,
            "ARCHIVO_ORIGEN": archivo_origen,
            "FECHA_CARGA": fecha_carga,
        }
        return datos

    def valor_python(self, valor):
        if valor is None or pd.isna(valor):
            return None
        if hasattr(valor, "item"):
            valor = valor.item()
        if hasattr(valor, "to_pydatetime"):
            valor = valor.to_pydatetime()
        return valor

    def texto(self, valor):
        return texto(valor)

    def texto_o_none(self, valor):
        texto = self.texto(valor)

        if texto == "" or texto.lower() == "nan":
            return None

        return texto

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
