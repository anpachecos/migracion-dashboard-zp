import pandas as pd
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.models import EstadoValidadorRaw, LogImportacion
from apps.dashboard.services.oracle_connection import obtener_conexion_oracle

class Command(BaseCommand):
    help = "Importa datos de validadores desde Oracle hacia SQLite"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Elimina los datos existentes en RAW antes de importar.",
        )

        parser.add_argument(
            "--dias",
            type=int,
            default=None,
            help="Cantidad de días hacia atrás para consultar. Ejemplo: --dias 14",
        )

        parser.add_argument(
            "--horas",
            type=int,
            default=2,
            help="Cantidad de horas hacia atrás para consultar. Por defecto: 2 horas.",
        )

    def handle(self, *args, **options):
        fecha_inicio = timezone.now()

        log = LogImportacion.objects.create(
            origen="ORACLE",
            estado="OK",
            fecha_inicio=fecha_inicio,
            mensaje="Importación Oracle iniciada",
        )
        
        filas_eliminadas = 0

        if options["limpiar"]:
            total_eliminados, _ = EstadoValidadorRaw.objects.all().delete()
            filas_eliminadas = total_eliminados

            self.stdout.write(
                self.style.WARNING(f"Registros eliminados: {total_eliminados}")
            )

        dias = options["dias"]
        horas = options["horas"]

        if dias is not None:
            modo_consulta = f"Últimos {dias} días"
        else:
            modo_consulta = f"Últimas {horas} horas"

        query = self.obtener_query(dias=dias, horas=horas)

        self.stdout.write(f"Modo de consulta: {modo_consulta}")

        self.stdout.write("Conectando a Oracle...")

        try:
            with obtener_conexion_oracle() as conexion:
                df = pd.read_sql(query, conexion)

            self.stdout.write(
                self.style.SUCCESS(f"Consulta Oracle OK. Filas obtenidas: {len(df)}")
            )

        except Exception as error:
            log.estado = "ERROR"
            log.fecha_fin = timezone.now()
            log.mensaje = f"Error consultando Oracle: {error}"
            log.filas_eliminadas = filas_eliminadas
            log.save()

            self.stderr.write(
                self.style.ERROR(f"Error consultando Oracle: {error}")
            )
            return

        registros = []

        for _, fila in df.iterrows():
            registro = EstadoValidadorRaw(
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

        cantidad_antes = EstadoValidadorRaw.objects.count()

        EstadoValidadorRaw.objects.bulk_create(
            registros,
            batch_size=500,
            ignore_conflicts=True
        )

        cantidad_despues = EstadoValidadorRaw.objects.count()
        filas_creadas = cantidad_despues - cantidad_antes
        filas_duplicadas = len(registros) - filas_creadas

        self.stdout.write(
            self.style.SUCCESS(
                f"Importación Oracle a RAW completada. "
                f"Obtenidos: {len(df)} | "
                f"Creados: {filas_creadas} | "
                f"Duplicados ignorados: {filas_duplicadas}"
            )
        )
        
        log.filas_obtenidas = len(df)
        log.filas_creadas = filas_creadas
        log.filas_eliminadas = filas_eliminadas
        log.mensaje = (
            "Importación Oracle a RAW completada correctamente. "
            f"Modo consulta: {modo_consulta}. "
            f"Duplicados ignorados: {filas_duplicadas}"
        )
        log.save()

    def obtener_query(self, dias=None, horas=2):
        if dias is not None:
            filtro_fecha = f"e.edt_dfechastatus >= TRUNC(SYSDATE) - {int(dias)}"
        else:
            filtro_fecha = f"e.edt_dfechastatus >= SYSDATE - ({int(horas)}/24)"

        query = """
            SELECT
                datos.AMID,
                MAX(datos.FEC_DESCARGA) AS FEC_DESCARGA,
                MAX(datos.FEC_ESTADO) AS FEC_ESTADO,
                MAX(datos.BUSID) AS BUSID,
                MAX(datos.OP) AS OP,
                MAX(datos.VERSION) AS VERSION,
                MAX(datos.PATENTE) AS PATENTE,
                MAX(datos.TD01) AS TD01,
                MAX(datos.TD04) AS TD04,
                MAX(datos.TABLA) AS TABLA,
                MAX(datos.VER_TABLA) AS VER_TABLA,
                TO_CHAR(datos.FECHA_HORA_REAL, 'DD-MM-YYYY HH24:MI:SS') AS FECHA_HORA,
                MAX(CASE WHEN datos.CLAVE = 'isContieneBateria' THEN datos.VALOR END) AS IS_CONTIENE_BATERIA,
                MAX(CASE WHEN datos.CLAVE = 'isContieneGps' THEN datos.VALOR END) AS IS_CONTIENE_GPS,
                MAX(CASE WHEN datos.CLAVE = 'isContieneTiempoVida' THEN datos.VALOR END) AS IS_CONTIENE_TIEMPO_VIDA,
                MAX(CASE WHEN datos.CLAVE = 'isErrorObtenerBateria' THEN datos.VALOR END) AS IS_ERROR_OBTENER_BATERIA,
                MAX(CASE WHEN datos.CLAVE = 'isErrorObtenerGps' THEN datos.VALOR END) AS IS_ERROR_OBTENER_GPS,
                MAX(CASE WHEN datos.CLAVE = 'isErrorObtenerTiempoVida' THEN datos.VALOR END) AS IS_ERROR_OBTENER_TIEMPO_VIDA,
                MAX(CASE WHEN datos.CLAVE = 'latitud' THEN datos.VALOR END) AS LATITUD,
                MAX(CASE WHEN datos.CLAVE = 'longitud' THEN datos.VALOR END) AS LONGITUD,
                MAX(CASE WHEN datos.CLAVE = 'porcentajeBateria' THEN datos.VALOR END) AS PORCENTAJE_BATERIA,
                MAX(CASE WHEN datos.CLAVE = 'tiempoVida' THEN datos.VALOR END) AS TIEMPO_VIDA,
                SYSDATE AS FECHA_REGISTRO
            FROM (
                SELECT
                    a.ata_nidas AS AMID,
                    TO_CHAR(a.ata_dfecultdescarga, 'dd/mm/yyyy hh24:mi:ss') AS FEC_DESCARGA,
                    TO_CHAR(a.ata_dfecultestado, 'dd/mm/yyyy hh24:mi:ss') AS FEC_ESTADO,
                    a.ata_nidsitio AS BUSID,
                    a.ata_nidentidad AS OP,
                    a.ata_sveraplicacion AS VERSION,
                    a.ata_snomsitio AS PATENTE,
                    a.ata_nidversiontd1 AS TD01,
                    a.ata_nidversiontd4 AS TD04,
                    e.edt_ntabladifusion AS TABLA,
                    e.edt_sversiontabla AS VER_TABLA,
                    e.edt_dfechastatus AS FECHA_HORA_REAL,
                    SUBSTR(e.edt_snombrecomponente, 2, INSTR(e.edt_snombrecomponente, '":') - 2) AS CLAVE,
                    REPLACE(REPLACE(REPLACE(REPLACE(SUBSTR(e.edt_snombrecomponente, INSTR(e.edt_snombrecomponente, ':') + 1), '"', ''), '}', ''), 'T', ' '), 'Z', '') AS VALOR
                FROM dbtablero.antena_tablero a
                LEFT JOIN dbtablero.estado_ds_tablero e
                    ON a.ata_nidas = e.edt_nidval
                WHERE a.ata_nidas > 7500000
                AND e.edt_ntabladifusion = 16
                AND e.edt_snombrecomponente IS NOT NULL
                AND __FILTRO_FECHA__
                AND (
                    e.edt_snombrecomponente LIKE '%"isContieneBateria":%'
                    OR e.edt_snombrecomponente LIKE '%"isContieneGps":%'
                    OR e.edt_snombrecomponente LIKE '%"isContieneTiempoVida":%'
                    OR e.edt_snombrecomponente LIKE '%"isErrorObtenerBateria":%'
                    OR e.edt_snombrecomponente LIKE '%"isErrorObtenerGps":%'
                    OR e.edt_snombrecomponente LIKE '%"isErrorObtenerTiempoVida":%'
                    OR e.edt_snombrecomponente LIKE '%"latitud":%'
                    OR e.edt_snombrecomponente LIKE '%"longitud":%'
                    OR e.edt_snombrecomponente LIKE '%"porcentajeBateria":%'
                    OR e.edt_snombrecomponente LIKE '%"tiempoVida":%'
                )
            ) datos
            GROUP BY datos.AMID, datos.FECHA_HORA_REAL
            ORDER BY datos.AMID, datos.FECHA_HORA_REAL
            """

        return query.replace("__FILTRO_FECHA__", filtro_fecha)

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