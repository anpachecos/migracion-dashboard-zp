import logging
import time
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.core.management import call_command
from django.db import OperationalError
from django.utils import timezone

from apps.dashboard.models import LogImportacion

# Para importar ubicaciones esperadas desde Excel manualmente, se ejecuta el comando:
# python manage.py importar_ubicaciones_esperadas

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
scheduler_started = False

job_validadores_running = False
job_ubicaciones_running = False


def es_error_database_locked(error):
    """
    Detecta el error típico de SQLite cuando la base está ocupada.
    """
    return "database is locked" in str(error).lower()


def ejecutar_comando_con_reintentos(nombre_comando, *args, max_intentos=3, esperas=None):
    """
    Ejecuta un comando Django con reintentos solo si falla por 'database is locked'.

    Ejemplo:
    - intento 1 falla
    - espera 10 segundos
    - intento 2 falla
    - espera 20 segundos
    - intento 3 falla
    - lanza el error final
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


def actualizar_validadores_job():
    global job_validadores_running

    if job_validadores_running:
        logger.warning("La actualización de validadores ya está en ejecución. Se omite esta corrida.")
        return

    job_validadores_running = True
    inicio = timezone.now()

    try:
        logger.info("Iniciando actualización automática de validadores...")

        ejecutar_comando_con_reintentos(
            "actualizar_validadores",
            max_intentos=3,
            esperas=[10, 20, 30],
        )

        logger.info("Actualización automática de validadores finalizada correctamente.")

    except Exception as error:
        logger.exception("Error en actualización automática de validadores.")

        LogImportacion.objects.create(
            origen="ORACLE",
            estado="ERROR",
            fecha_inicio=inicio,
            fecha_fin=timezone.now(),
            mensaje=f"Error en scheduler automático de validadores: {error}",
        )

    finally:
        job_validadores_running = False


def importar_ubicaciones_esperadas_job():
    global job_ubicaciones_running

    if job_ubicaciones_running:
        logger.warning("La importación de ubicaciones esperadas ya está en ejecución. Se omite esta corrida.")
        return

    job_ubicaciones_running = True
    inicio = timezone.now()

    try:
        ruta_excel = Path(settings.BASE_DIR) / "VERSION ZONA PAGA.xlsx"

        if not ruta_excel.exists():
            mensaje = f"No se encontró el archivo de ubicaciones esperadas: {ruta_excel}"
            logger.warning(mensaje)

            LogImportacion.objects.create(
                origen="EXCEL_UBICACIONES",
                estado="ERROR",
                fecha_inicio=inicio,
                fecha_fin=timezone.now(),
                mensaje=mensaje,
            )
            return

        logger.info(f"Iniciando importación automática de ubicaciones esperadas desde: {ruta_excel}")

        ejecutar_comando_con_reintentos(
            "importar_ubicaciones_esperadas",
            str(ruta_excel),
            max_intentos=3,
            esperas=[10, 20, 30],
        )

        logger.info("Importación automática de ubicaciones esperadas finalizada correctamente.")

    except Exception as error:
        logger.exception("Error en importación automática de ubicaciones esperadas.")

        LogImportacion.objects.create(
            origen="EXCEL_UBICACIONES",
            estado="ERROR",
            fecha_inicio=inicio,
            fecha_fin=timezone.now(),
            mensaje=f"Error en scheduler automático de ubicaciones esperadas: {error}",
        )

    finally:
        job_ubicaciones_running = False


def iniciar_scheduler():
    global scheduler_started

    if scheduler_started:
        return

    scheduler.add_job(
        actualizar_validadores_job,
        trigger="cron",
        minute="0,30",
        id="actualizar_validadores_cada_30_min",
        replace_existing=True,
        max_instances=1,
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

    scheduler.start()
    scheduler_started = True

    logger.info("Scheduler iniciado.")
    logger.info("Job validadores: cada 30 minutos.")
    logger.info("Job ubicaciones esperadas: todos los días a las 18:45.")