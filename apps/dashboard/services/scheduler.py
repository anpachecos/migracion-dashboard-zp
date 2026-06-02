import logging
from django.conf import settings
from apscheduler.schedulers.background import BackgroundScheduler
from django.core.management import call_command
from django.utils import timezone

from apps.dashboard.models import LogImportacion


logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
scheduler_started = False
job_running = False


def actualizar_validadores_job():
    global job_running

    if job_running:
        logger.warning("La actualización de validadores ya está en ejecución. Se omite esta corrida.")
        return

    job_running = True
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
            mensaje=f"Error en scheduler automático: {error}",
        )

    finally:
        job_running = False


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

    scheduler.start()
    scheduler_started = True

    logger.info("Scheduler de validadores iniciado. Frecuencia: cada 30 minutos.")