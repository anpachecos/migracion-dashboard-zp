import logging
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from apps.dashboard.models import LogImportacion

#Para importar ubicaciones esperadas desde Excel manualmente, se ejecuta el comando:
#python manage.py importar_ubicaciones_esperadas

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
scheduler_started = False

job_validadores_running = False
job_ubicaciones_running = False


def actualizar_validadores_job():
    global job_validadores_running

    if job_validadores_running:
        logger.warning("La actualización de validadores ya está en ejecución. Se omite esta corrida.")
        return

    job_validadores_running = True
    inicio = timezone.now()

    try:
        logger.info("Iniciando actualización automática de validadores...")

        call_command("actualizar_validadores")

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

        call_command("importar_ubicaciones_esperadas", str(ruta_excel))

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
        hour=8,
        minute=30,
        id="importar_ubicaciones_esperadas_diario",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    scheduler_started = True

    logger.info("Scheduler iniciado.")
    logger.info("Job validadores: cada 30 minutos.")
    logger.info("Job ubicaciones esperadas: todos los días a las 08:30.")