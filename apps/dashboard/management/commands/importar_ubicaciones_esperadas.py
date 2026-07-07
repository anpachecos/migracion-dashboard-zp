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

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


LATITUD_LABORATORIO_ZP = -33.437191
LONGITUD_LABORATORIO_ZP = -70.656102
RADIO_LABORATORIO_ZP = 150
NOMBRE_LABORATORIO_ZP = "Laboratorio Zonas Pagas"


COLUMNAS_ORACLE = [
    "AMID",
    "CODIGO_ZP_TS",
    "COD_PARADA1",
    "COD_PARADA2",
    "NOMBRE",
    "COMUNA",
    "UNIDAD",
    "OPERADOR",
    "UN",
    "UN_SECUNDARIA_1",
    "UN_SECUNDARIA_2",
    "UN_SECUNDARIA_3",
    "PST",
    "SERVICIOS",
    "TOTAL_VAL_VIGENTES_ZP",
    "HORARIO",
    "HORARIO_LABORAL_PM",
    "HORARIO_SABADO",
    "HORARIO_DOMINGO",
    "INICIO_OPERACION",
    "FIN_OPERACION",
    "PATENTE",
    "OP_ID",
    "BUS_ID",
    "SERIE_VALIDADOR",
    "IDDS",
    "NUM_VAL",
    "LATITUD_ESPERADA",
    "LONGITUD_ESPERADA",
    "X",
    "Y",
    "OPERATIVA",
    "CONTINGENCIA",
    "MIXTA",
    "RADIO_METROS",
    "TIPO",
    "RENOVADA",
    "VERSION_ZP",
    "ARCHIVO_ORIGEN",
    "FECHA_CARGA",
]

COLUMNAS_HISTORIAL = [
    "AMID",
    "CODIGO_ZP_TS",
    "COD_PARADA1",
    "COD_PARADA2",
    "NOMBRE",
    "COMUNA",
    "UNIDAD",
    "OPERADOR",
    "UN",
    "UN_SECUNDARIA_1",
    "UN_SECUNDARIA_2",
    "UN_SECUNDARIA_3",
    "PST",
    "SERVICIOS",
    "TOTAL_VAL_VIGENTES_ZP",
    "HORARIO",
    "HORARIO_LABORAL_PM",
    "HORARIO_SABADO",
    "HORARIO_DOMINGO",
    "INICIO_OPERACION",
    "FIN_OPERACION",
    "PATENTE",
    "OP_ID",
    "BUS_ID",
    "SERIE_VALIDADOR",
    "IDDS",
    "NUM_VAL",
    "LATITUD_ESPERADA",
    "LONGITUD_ESPERADA",
    "X",
    "Y",
    "OPERATIVA",
    "CONTINGENCIA",
    "MIXTA",
    "RADIO_METROS",
    "TIPO",
    "RENOVADA",
    "ORIGEN_UBICACION",
    "VERSION_ZP",
    "ARCHIVO_ORIGEN",
    "FECHA_INICIO_VIGENCIA",
    "FECHA_FIN_VIGENCIA",
    "FECHA_CARGA",
]


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
        fecha_carga = self.ahora_oracle()
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

        archivo_origen = ruta_excel.name
        version_zp = self.extraer_version_desde_nombre(archivo_origen)

        self.stdout.write(f"Leyendo archivo: {ruta_excel}")
        self.stdout.write("Hoja utilizada: Version_DB")
        self.stdout.write(f"Versión detectada: {version_zp or 'Sin versión'}")

        try:
            df = pd.read_excel(ruta_excel, sheet_name="Version_DB")
        except ValueError:
            self.stderr.write(
                self.style.ERROR("No se encontró la hoja Version_DB en el Excel.")
            )
            return

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
            self.stderr.write(
                self.style.ERROR(f"Faltan columnas requeridas en el Excel: {faltantes}")
            )
            return

        creados_vigente = 0
        actualizados_vigente = 0
        omitidos = 0
        nuevos_historial = 0
        cerrados_historial = 0
        sin_cambios_historial = 0

        amids_excel = set()

        try:
            with obtener_conexion_oracle() as conexion:
                with conexion.cursor() as cursor:
                    for _, fila in df.iterrows():
                        datos = self.normalizar_fila(
                            fila=fila,
                            fecha_carga=fecha_carga,
                            archivo_origen=archivo_origen,
                            version_zp=version_zp,
                        )

                        if datos is None:
                            omitidos += 1
                            continue

                        amid = datos["AMID"]
                        amids_excel.add(amid)

                        existe_vigente = self.existe_vigente(cursor, amid)

                        self.upsert_vigente(cursor, datos)

                        if existe_vigente:
                            actualizados_vigente += 1
                        else:
                            creados_vigente += 1

                        resultado_historial = self.actualizar_historial(
                            cursor=cursor,
                            datos=datos,
                            fecha_carga=fecha_carga,
                        )

                        if resultado_historial == "nuevo":
                            nuevos_historial += 1
                        elif resultado_historial == "cerrado_y_nuevo":
                            cerrados_historial += 1
                            nuevos_historial += 1
                        elif resultado_historial == "sin_cambios":
                            sin_cambios_historial += 1

                    (
                        movidos_laboratorio,
                        cerrados_por_ausencia,
                        historicos_por_ausencia,
                    ) = self.mover_ausentes_a_laboratorio(
                        cursor=cursor,
                        amids_excel=amids_excel,
                        fecha_carga=fecha_carga,
                        archivo_origen=archivo_origen,
                        version_zp=version_zp,
                    )

                    cerrados_historial += cerrados_por_ausencia
                    nuevos_historial += historicos_por_ausencia

                conexion.commit()

        except Exception as error:
            self.stderr.write(
                self.style.ERROR(f"Error importando ubicaciones a Oracle: {error}")
            )
            return

        self.stdout.write(self.style.SUCCESS("Importación completada en Oracle."))
        self.stdout.write(f"Fecha carga: {fecha_carga.strftime('%d-%m-%Y %H:%M:%S')}")
        self.stdout.write(f"Archivo origen: {archivo_origen}")
        self.stdout.write(f"Versión ZP: {version_zp or 'Sin versión'}")
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
            columna for columna in COLUMNAS_ORACLE
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

    def existe_vigente(self, cursor, amid):
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
            WHERE AMID = :amid
            """,
            {"amid": amid}
        )

        return cursor.fetchone()[0] > 0

    def upsert_vigente(self, cursor, datos):
        columnas_update = [
            columna for columna in COLUMNAS_ORACLE
            if columna != "AMID"
        ]

        set_sql = ", ".join([
            f"{columna} = :{columna}"
            for columna in columnas_update
        ])

        columnas_insert = ", ".join(COLUMNAS_ORACLE)
        valores_insert = ", ".join([f":{columna}" for columna in COLUMNAS_ORACLE])

        sql = f"""
            MERGE INTO USR_LAB.UBICACION_ESPERADA_VALIDADOR destino
            USING (
                SELECT :AMID AS AMID FROM DUAL
            ) origen
            ON (destino.AMID = origen.AMID)
            WHEN MATCHED THEN
                UPDATE SET {set_sql}
            WHEN NOT MATCHED THEN
                INSERT ({columnas_insert})
                VALUES ({valores_insert})
        """

        parametros = {
            columna: datos.get(columna)
            for columna in COLUMNAS_ORACLE
        }

        cursor.execute(sql, parametros)

    def actualizar_historial(self, cursor, datos, fecha_carga):
        historial_vigente = self.obtener_historial_vigente(cursor, datos["AMID"])

        if historial_vigente is None:
            self.crear_historial(cursor, datos, fecha_carga)
            return "nuevo"

        if self.historial_es_igual(historial_vigente, datos):
            return "sin_cambios"

        cursor.execute(
            """
            UPDATE USR_LAB.HISTORIAL_UBICACION_ESPERADA
            SET FECHA_FIN_VIGENCIA = :fecha_carga
            WHERE ID = :id
            """,
            {
                "fecha_carga": fecha_carga,
                "id": historial_vigente["ID"],
            }
        )

        self.crear_historial(cursor, datos, fecha_carga)

        return "cerrado_y_nuevo"

    def obtener_historial_vigente(self, cursor, amid):
        cursor.execute(
            """
            SELECT
                ID,
                AMID,
                NOMBRE,
                SERIE_VALIDADOR,
                LATITUD_ESPERADA,
                LONGITUD_ESPERADA,
                RADIO_METROS,
                OPERATIVA,
                ORIGEN_UBICACION,
                VERSION_ZP
            FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA
            WHERE AMID = :amid
              AND FECHA_FIN_VIGENCIA IS NULL
            ORDER BY FECHA_INICIO_VIGENCIA DESC
            """,
            {"amid": amid}
        )

        fila = cursor.fetchone()

        if not fila:
            return None

        columnas = [col[0] for col in cursor.description]
        return dict(zip(columnas, fila))

    def crear_historial(self, cursor, datos, fecha_carga):
        datos_historial = {
            columna: datos.get(columna)
            for columna in COLUMNAS_HISTORIAL
        }

        datos_historial["FECHA_INICIO_VIGENCIA"] = fecha_carga
        datos_historial["FECHA_FIN_VIGENCIA"] = None

        columnas_insert = ", ".join(COLUMNAS_HISTORIAL)
        valores_insert = ", ".join([f":{columna}" for columna in COLUMNAS_HISTORIAL])

        cursor.execute(
            f"""
            INSERT INTO USR_LAB.HISTORIAL_UBICACION_ESPERADA (
                {columnas_insert}
            )
            VALUES (
                {valores_insert}
            )
            """,
            datos_historial
        )

    def historial_es_igual(self, historial, datos):
        return (
            self.texto(historial.get("NOMBRE")) == self.texto(datos.get("NOMBRE"))
            and self.texto(historial.get("SERIE_VALIDADOR")) == self.texto(datos.get("SERIE_VALIDADOR"))
            and self.numero_igual(historial.get("LATITUD_ESPERADA"), datos.get("LATITUD_ESPERADA"))
            and self.numero_igual(historial.get("LONGITUD_ESPERADA"), datos.get("LONGITUD_ESPERADA"))
            and self.numero_igual(historial.get("RADIO_METROS"), datos.get("RADIO_METROS"))
            and self.valor_entero(historial.get("OPERATIVA")) == self.valor_entero(datos.get("OPERATIVA"))
            and self.texto(historial.get("ORIGEN_UBICACION")) == self.texto(datos.get("ORIGEN_UBICACION"))
            and self.texto(historial.get("VERSION_ZP")) == self.texto(datos.get("VERSION_ZP"))
        )

    def mover_ausentes_a_laboratorio(self, cursor, amids_excel, fecha_carga, archivo_origen, version_zp):
        movidos = 0
        cerrados_historial = 0
        nuevos_historial = 0

        cursor.execute(
            """
            SELECT
                AMID,
                SERIE_VALIDADOR
            FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
            """
        )

        filas_vigentes = cursor.fetchall()
        columnas = [col[0] for col in cursor.description]

        for fila in filas_vigentes:
            vigente = dict(zip(columnas, fila))
            amid = str(vigente["AMID"]).strip()

            if amid in amids_excel:
                continue

            datos_laboratorio = {
                columna: None
                for columna in COLUMNAS_ORACLE
            }

            datos_laboratorio.update({
                "AMID": amid,
                "NOMBRE": NOMBRE_LABORATORIO_ZP,
                "SERIE_VALIDADOR": vigente.get("SERIE_VALIDADOR"),
                "IDDS": amid,
                "LATITUD_ESPERADA": LATITUD_LABORATORIO_ZP,
                "LONGITUD_ESPERADA": LONGITUD_LABORATORIO_ZP,
                "RADIO_METROS": RADIO_LABORATORIO_ZP,
                "OPERATIVA": 0,
                "VERSION_ZP": version_zp,
                "ARCHIVO_ORIGEN": archivo_origen,
                "FECHA_CARGA": fecha_carga,
                "ORIGEN_UBICACION": "laboratorio_default",
            })

            historial_vigente = self.obtener_historial_vigente(cursor, amid)

            ya_esta_en_laboratorio = (
                historial_vigente
                and self.texto(historial_vigente.get("NOMBRE")) == self.texto(NOMBRE_LABORATORIO_ZP)
                and self.numero_igual(historial_vigente.get("LATITUD_ESPERADA"), LATITUD_LABORATORIO_ZP)
                and self.numero_igual(historial_vigente.get("LONGITUD_ESPERADA"), LONGITUD_LABORATORIO_ZP)
                and self.numero_igual(historial_vigente.get("RADIO_METROS"), RADIO_LABORATORIO_ZP)
                and self.valor_entero(historial_vigente.get("OPERATIVA")) == 0
            )

            if ya_esta_en_laboratorio:
                continue

            self.upsert_vigente(cursor, datos_laboratorio)
            movidos += 1

            if historial_vigente:
                cursor.execute(
                    """
                    UPDATE USR_LAB.HISTORIAL_UBICACION_ESPERADA
                    SET FECHA_FIN_VIGENCIA = :fecha_carga
                    WHERE ID = :id
                    """,
                    {
                        "fecha_carga": fecha_carga,
                        "id": historial_vigente["ID"],
                    }
                )
                cerrados_historial += 1

            datos_historial = dict(datos_laboratorio)
            datos_historial["ORIGEN_UBICACION"] = "laboratorio_default"

            self.crear_historial(cursor, datos_historial, fecha_carga)
            nuevos_historial += 1

        return movidos, cerrados_historial, nuevos_historial

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

    def valor_entero(self, valor):
        if valor is None or pd.isna(valor):
            return None

        try:
            return int(float(valor))
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

    def numero_igual(self, valor_1, valor_2):
        if valor_1 is None and valor_2 is None:
            return True

        if valor_1 is None or valor_2 is None:
            return False

        try:
            return round(float(valor_1), 7) == round(float(valor_2), 7)
        except (ValueError, TypeError):
            return False