"""
Comando Django: registrar_estado_oracle.py

Registra en SQLite un resumen del estado de las tablas Oracle usadas por el dashboard.

Actualmente revisa:
- USR_LAB.BATERIA_BLOQUE_30MIN
- USR_LAB.UBICACION_ESPERADA_VALIDADOR
- USR_LAB.HISTORIAL_UBICACION_ESPERADA

No modifica Oracle. Solo consulta y guarda logs internos.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle
from apps.dashboard.services.logs_service import registrar_log_importacion


class Command(BaseCommand):
    help = "Registra estado de tablas Oracle en logs internos SQLite."

    def handle(self, *args, **options):
        fecha_inicio = timezone.now()

        try:
            with obtener_conexion_oracle() as conexion:
                with conexion.cursor() as cursor:
                    resumen_bateria = self.obtener_resumen_bateria(cursor)
                    resumen_ubicaciones = self.obtener_resumen_ubicaciones(cursor)
                    resumen_historial = self.obtener_resumen_historial(cursor)

            self.registrar_log_bateria(
                fecha_inicio=fecha_inicio,
                resumen=resumen_bateria,
            )

            self.registrar_log_ubicaciones(
                fecha_inicio=fecha_inicio,
                resumen_ubicaciones=resumen_ubicaciones,
                resumen_historial=resumen_historial,
            )

            mensaje_general = (
                "Estado Oracle registrado correctamente. "
                f"Batería bloques: {resumen_bateria['total_bloques']}. "
                f"Bloques con dato: {resumen_bateria['bloques_con_dato']}. "
                f"Ubicaciones vigentes: {resumen_ubicaciones['total_ubicaciones']}. "
                f"Historial vigente: {resumen_historial['historiales_vigentes']}."
            )

            registrar_log_importacion(
                origen="ESTADO_ORACLE",
                estado="OK",
                fecha_inicio=fecha_inicio,
                fecha_fin=timezone.now(),
                filas_obtenidas=resumen_bateria["total_bloques"],
                filas_creadas=0,
                filas_eliminadas=0,
                mensaje=mensaje_general,
            )

            self.stdout.write(self.style.SUCCESS(mensaje_general))

        except Exception as error:
            mensaje = f"Error registrando estado Oracle: {error}"

            registrar_log_importacion(
                origen="ESTADO_ORACLE",
                estado="ERROR",
                fecha_inicio=fecha_inicio,
                fecha_fin=timezone.now(),
                mensaje=mensaje,
            )

            self.stderr.write(self.style.ERROR(mensaje))

    def obtener_resumen_bateria(self, cursor):
        query = """
            SELECT
                COUNT(*) AS TOTAL_BLOQUES,
                SUM(
                    CASE
                        WHEN TIENE_DATO = 1 THEN 1
                        ELSE 0
                    END
                ) AS BLOQUES_CON_DATO,
                MAX(FECHA_HORA_BLOQUE) AS ULTIMO_BLOQUE,
                MAX(
                    CASE
                        WHEN TIENE_DATO = 1 THEN FECHA_HORA_BLOQUE
                    END
                ) AS ULTIMO_BLOQUE_CON_DATO,
                MAX(FECHA_ACTUALIZACION) AS ULTIMA_ACTUALIZACION
            FROM USR_LAB.BATERIA_BLOQUE_30MIN
        """

        cursor.execute(query)
        fila = cursor.fetchone()

        return {
            "total_bloques": int(fila[0] or 0),
            "bloques_con_dato": int(fila[1] or 0),
            "ultimo_bloque": fila[2],
            "ultimo_bloque_con_dato": fila[3],
            "ultima_actualizacion": fila[4],
        }

    def obtener_resumen_ubicaciones(self, cursor):
        query = """
            SELECT
                COUNT(*) AS TOTAL_UBICACIONES,
                MAX(FECHA_CARGA) AS ULTIMA_CARGA
            FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
        """

        cursor.execute(query)
        fila = cursor.fetchone()

        return {
            "total_ubicaciones": int(fila[0] or 0),
            "ultima_carga": fila[1],
        }

    def obtener_resumen_historial(self, cursor):
        query = """
            SELECT
                COUNT(*) AS HISTORIALES_VIGENTES
            FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA
            WHERE FECHA_FIN_VIGENCIA IS NULL
        """

        cursor.execute(query)
        fila = cursor.fetchone()

        return {
            "historiales_vigentes": int(fila[0] or 0),
        }

    def texto_fecha(self, fecha):
        if not fecha:
            return "Sin datos"

        return fecha.strftime("%d-%m-%Y %H:%M:%S")

    def registrar_log_bateria(self, fecha_inicio, resumen):
        mensaje = (
            "Estado batería bloques Oracle. "
            f"Total bloques: {resumen['total_bloques']}. "
            f"Bloques con dato: {resumen['bloques_con_dato']}. "
            f"Último bloque: {self.texto_fecha(resumen['ultimo_bloque'])}. "
            f"Último bloque con dato: {self.texto_fecha(resumen['ultimo_bloque_con_dato'])}. "
            f"Última actualización tabla: {self.texto_fecha(resumen['ultima_actualizacion'])}."
        )

        registrar_log_importacion(
            origen="BATERIA_BLOQUES_ORACLE",
            estado="OK",
            fecha_inicio=fecha_inicio,
            fecha_fin=timezone.now(),
            filas_obtenidas=resumen["total_bloques"],
            filas_creadas=resumen["bloques_con_dato"],
            filas_eliminadas=0,
            mensaje=mensaje,
        )

    def registrar_log_ubicaciones(self, fecha_inicio, resumen_ubicaciones, resumen_historial):
        mensaje = (
            "Estado ubicaciones esperadas Oracle. "
            f"Ubicaciones vigentes: {resumen_ubicaciones['total_ubicaciones']}. "
            f"Última carga: {self.texto_fecha(resumen_ubicaciones['ultima_carga'])}. "
            f"Historiales vigentes: {resumen_historial['historiales_vigentes']}."
        )

        registrar_log_importacion(
            origen="UBICACIONES_ORACLE",
            estado="OK",
            fecha_inicio=fecha_inicio,
            fecha_fin=timezone.now(),
            filas_obtenidas=resumen_ubicaciones["total_ubicaciones"],
            filas_creadas=resumen_historial["historiales_vigentes"],
            filas_eliminadas=0,
            mensaje=mensaje,
        )