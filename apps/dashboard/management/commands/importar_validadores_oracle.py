import pandas as pd
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.models import EstadoValidador
from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


class Command(BaseCommand):
    help = "Importa datos de validadores desde Oracle hacia SQLite"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Elimina los datos existentes antes de importar.",
        )

    def handle(self, *args, **options):
        if options["limpiar"]:
            total_eliminados, _ = EstadoValidador.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"Registros eliminados: {total_eliminados}")
            )

        query = self.obtener_query()

        self.stdout.write("Conectando a Oracle...")

        try:
            with obtener_conexion_oracle() as conexion:
                df = pd.read_sql(query, conexion)

            self.stdout.write(
                self.style.SUCCESS(f"Consulta Oracle OK. Filas obtenidas: {len(df)}")
            )

        except Exception as error:
            self.stderr.write(
                self.style.ERROR(f"Error consultando Oracle: {error}")
            )
            return

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
            self.style.SUCCESS(f"Importación Oracle completada. Registros creados: {len(registros)}")
        )

    def obtener_query(self):
        return """
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
            MAX(datos.FECHA_HORA) AS FECHA_HORA,

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
                TO_CHAR(e.edt_dfechastatus, 'DD-MM-YYYY HH24:MI:SS') AS FECHA_HORA,

                SUBSTR(
                    e.edt_snombrecomponente,
                    2,
                    INSTR(e.edt_snombrecomponente, '":') - 2
                ) AS CLAVE,

                REPLACE(
                    REPLACE(
                        REPLACE(
                            REPLACE(
                                SUBSTR(
                                    e.edt_snombrecomponente,
                                    INSTR(e.edt_snombrecomponente, ':') + 1
                                ),
                                '"',
                                ''
                            ),
                            '}',
                            ''
                        ),
                        'T',
                        ' '
                    ),
                    'Z',
                    ''
                ) AS VALOR

            FROM dbtablero.antena_tablero a
            LEFT JOIN dbtablero.estado_ds_tablero e
                   ON a.ata_nidas = e.edt_nidval
            WHERE a.ata_nidas > 7500000
              AND e.edt_ntabladifusion = 16
              AND e.edt_snombrecomponente IS NOT NULL
              AND e.edt_dfechastatus >= TRUNC(SYSDATE) - 14
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

        GROUP BY datos.AMID
        ORDER BY datos.AMID
        """

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