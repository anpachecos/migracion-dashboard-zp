import logging
import time
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.core.management import call_command
from django.db import OperationalError
from django.utils import timezone

from apps.dashboard.services.logs_service import registrar_log_importacion

'''
Retención actual:
- BATERIA_BLOQUE_30MIN: 16 días, limpiado por PRC_ACTUALIZAR_BATERIA_BLOQUES.
- HISTORIAL_UBICACION_ESPERADA: 16 días para registros cerrados, limpiado por PRC_LIMPIAR_HIST_UBICACION.
- UBICACION_ESPERADA_VALIDADOR: tabla vigente, no se limpia por fecha.
- SQLite: solo usuarios, sesiones, permisos, admin, migraciones y logs.
'''
job_ubicaciones_running = False
job_estado_oracle_running = False

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
scheduler_started = False

job_ubicaciones_running = False

job_limpieza_historial_ubicacion_running = False

def es_error_database_locked(error):
    """
    Detecta el error típico de SQLite cuando la base está ocupada.
    """
    return "database is locked" in str(error).lower()


def ejecutar_comando_con_reintentos(nombre_comando, *args, max_intentos=3, esperas=None):
    """
    Ejecuta un comando Django con reintentos solo si falla por 'database is locked'.

    Esto se mantiene porque SQLite todavía se usa para:
    - usuarios
    - sesiones
    - logs internos
    """

    if esperas is None:
        esperas = [10, 20, 30]

    ultimo_error = None

    for intento in range(1, max_intentos + 1):
        try:
            logger.info(
                "Ejecutando comando %s. Intento %s de %s.",
                nombre_comando,
                intento,
                max_intentos,
            )

            call_command(nombre_comando, *args)

            logger.info(
                "Comando %s ejecutado correctamente en intento %s.",
                nombre_comando,
                intento,
            )

            return

        except OperationalError as error:
            ultimo_error = error

            if not es_error_database_locked(error):
                raise

            logger.warning(
                "SQLite ocupado al ejecutar %s. Intento %s de %s. Error: %s",
                nombre_comando,
                intento,
                max_intentos,
                error,
            )

        except Exception as error:
            ultimo_error = error

            if not es_error_database_locked(error):
                raise

            logger.warning(
                "Base de datos bloqueada al ejecutar %s. Intento %s de %s. Error: %s",
                nombre_comando,
                intento,
                max_intentos,
                error,
            )

        if intento < max_intentos:
            segundos_espera = esperas[min(intento - 1, len(esperas) - 1)]

            logger.info(
                "Esperando %s segundos antes de reintentar %s.",
                segundos_espera,
                nombre_comando,
            )

            time.sleep(segundos_espera)

    raise ultimo_error


def importar_ubicaciones_esperadas_job():
    """
    Importa diariamente las ubicaciones esperadas desde el Excel base.

    Nota:
    El comando importar_ubicaciones_esperadas ya registra el detalle del proceso
    en SQLite con origen UBICACIONES_ORACLE.
    Este job solo registra errores propios del scheduler, por ejemplo:
    - archivo no encontrado
    - excepción al ejecutar el comando
    """

    global job_ubicaciones_running

    if job_ubicaciones_running:
        logger.warning(
            "La importación de ubicaciones esperadas ya está en ejecución. "
            "Se omite esta corrida."
        )

        registrar_log_importacion(
            origen="SCHEDULER",
            estado="ADVERTENCIA",
            mensaje=(
                "Se omitió la importación automática de ubicaciones porque "
                "ya había una ejecución en curso."
            ),
        )

        return

    job_ubicaciones_running = True
    fecha_inicio = timezone.now()

    try:
        ruta_excel = Path(settings.BASE_DIR) / "VERSION ZONA PAGA.xlsx"

        if not ruta_excel.exists():
            mensaje = f"No se encontró el archivo de ubicaciones esperadas: {ruta_excel}"
            logger.warning(mensaje)

            registrar_log_importacion(
                origen="SCHEDULER",
                estado="ERROR",
                fecha_inicio=fecha_inicio,
                fecha_fin=timezone.now(),
                mensaje=mensaje,
            )

            return

        logger.info(
            "Iniciando importación automática de ubicaciones esperadas desde: %s",
            ruta_excel,
        )

        ejecutar_comando_con_reintentos(
            "importar_ubicaciones_esperadas",
            str(ruta_excel),
            max_intentos=3,
            esperas=[10, 20, 30],
        )

        logger.info(
            "Importación automática de ubicaciones esperadas finalizada. "
            "El detalle quedó registrado por el comando UBICACIONES_ORACLE."
        )

    except Exception as error:
        logger.exception("Error en importación automática de ubicaciones esperadas.")

        registrar_log_importacion(
            origen="SCHEDULER",
            estado="ERROR",
            fecha_inicio=fecha_inicio,
            fecha_fin=timezone.now(),
            mensaje=f"Error en scheduler automático de ubicaciones esperadas: {error}",
        )

    finally:
        job_ubicaciones_running = False

def registrar_estado_oracle_job():
    """
    Registra periódicamente el estado de las tablas Oracle usadas por el dashboard.

    Este job no modifica Oracle.
    Solo ejecuta el comando registrar_estado_oracle, que guarda logs en SQLite.
    """

    global job_estado_oracle_running

    if job_estado_oracle_running:
        logger.warning(
            "El registro de estado Oracle ya está en ejecución. "
            "Se omite esta corrida."
        )

        registrar_log_importacion(
            origen="SCHEDULER",
            estado="ADVERTENCIA",
            mensaje=(
                "Se omitió el registro de estado Oracle porque "
                "ya había una ejecución en curso."
            ),
        )

        return

    job_estado_oracle_running = True
    fecha_inicio = timezone.now()

    try:
        logger.info("Iniciando registro automático de estado Oracle...")

        ejecutar_comando_con_reintentos(
            "registrar_estado_oracle",
            max_intentos=3,
            esperas=[10, 20, 30],
        )

        logger.info("Registro automático de estado Oracle finalizado correctamente.")

    except Exception as error:
        logger.exception("Error registrando estado Oracle desde scheduler.")

        registrar_log_importacion(
            origen="SCHEDULER",
            estado="ERROR",
            fecha_inicio=fecha_inicio,
            fecha_fin=timezone.now(),
            mensaje=f"Error registrando estado Oracle desde scheduler: {error}",
        )

    finally:
        job_estado_oracle_running = False

def limpiar_historial_ubicacion_oracle_job():
    """
    Limpia diariamente el historial cerrado antiguo de ubicaciones esperadas en Oracle.

    No borra vigencias actuales porque el procedure Oracle solo elimina registros
    con FECHA_FIN_VIGENCIA IS NOT NULL.
    """

    global job_limpieza_historial_ubicacion_running

    if job_limpieza_historial_ubicacion_running:
        logger.warning(
            "La limpieza de historial de ubicaciones Oracle ya está en ejecución. "
            "Se omite esta corrida."
        )

        registrar_log_importacion(
            origen="SCHEDULER",
            estado="ADVERTENCIA",
            mensaje=(
                "Se omitió la limpieza de historial de ubicaciones Oracle "
                "porque ya había una ejecución en curso."
            ),
        )

        return

    job_limpieza_historial_ubicacion_running = True
    fecha_inicio = timezone.now()

    try:
        logger.info("Iniciando limpieza automática de historial de ubicaciones Oracle...")

        ejecutar_comando_con_reintentos(
            "limpiar_historial_ubicacion_oracle",
            "--dias-retencion",
            "16",
            max_intentos=3,
            esperas=[10, 20, 30],
        )

        logger.info("Limpieza automática de historial de ubicaciones Oracle finalizada.")

    except Exception as error:
        logger.exception("Error limpiando historial de ubicaciones Oracle desde scheduler.")

        registrar_log_importacion(
            origen="SCHEDULER",
            estado="ERROR",
            fecha_inicio=fecha_inicio,
            fecha_fin=timezone.now(),
            mensaje=f"Error limpiando historial de ubicaciones Oracle desde scheduler: {error}",
        )

    finally:
        job_limpieza_historial_ubicacion_running = False

def iniciar_scheduler():
    """
    Inicia los jobs internos del dashboard.

    Actualmente:
    - Estado Oracle: cada 30 minutos.
    - Ubicaciones esperadas: todos los días a las 18:45.
    """

    global scheduler_started

    if scheduler_started:
        return

    scheduler.add_job(
        registrar_estado_oracle_job,
        trigger="cron",
        minute="5,35",
        id="registrar_estado_oracle_cada_30_min",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
        coalesce=True,
    )

    scheduler.add_job(
        importar_ubicaciones_esperadas_job,
        trigger="cron",
        hour=18,
        minute=45,
        id="importar_ubicaciones_esperadas_diario",
        replace_existing=True,
        max_instances=1,
    )
    
    scheduler.add_job(
        limpiar_historial_ubicacion_oracle_job,
        trigger="cron",
        hour=19,
        minute=10,
        id="limpiar_historial_ubicacion_oracle_diario",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    scheduler_started = True

    logger.info("Scheduler iniciado.")
    logger.info("Job estado Oracle: cada 30 minutos, minutos 5 y 35.")
    logger.info("Job ubicaciones esperadas: todos los días a las 18:45.")
    logger.info("Job limpieza historial ubicaciones Oracle: todos los días a las 19:10.")
    registrar_log_importacion(
        origen="SCHEDULER",
        estado="INFO",
        mensaje=(
            "Scheduler iniciado. "
            "Job estado Oracle programado cada 30 minutos. "
            "Job ubicaciones esperadas programado todos los días a las 18:45."
        ),
    )