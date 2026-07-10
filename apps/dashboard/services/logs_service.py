import logging

from django.utils import timezone
from django.db import OperationalError

from apps.dashboard.models import LogImportacion


logger = logging.getLogger(__name__)


def registrar_log_importacion(
    origen,
    estado,
    fecha_inicio=None,
    fecha_fin=None,
    filas_obtenidas=0,
    filas_creadas=0,
    filas_eliminadas=0,
    mensaje="",
):
    """
    Registra un log interno del sistema en SQLite.

    Esta función centraliza los logs para procesos como:
    - pruebas de conexión Oracle
    - carga de ubicaciones esperadas
    - revisión de tablas Oracle
    - scheduler
    - exportaciones Excel

    Importante:
    Si falla el registro del log, no debe botar el proceso principal.
    """

    if fecha_inicio is None:
        fecha_inicio = timezone.now()

    if fecha_fin is None:
        fecha_fin = timezone.now()

    try:
        return LogImportacion.objects.create(
            origen=origen,
            estado=estado,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            filas_obtenidas=filas_obtenidas or 0,
            filas_creadas=filas_creadas or 0,
            filas_eliminadas=filas_eliminadas or 0,
            mensaje=mensaje or "",
        )

    except OperationalError as error:
        logger.warning(
            "No se pudo registrar log por error operacional en SQLite: %s",
            error,
        )

    except Exception as error:
        logger.exception(
            "No se pudo registrar log interno del sistema: %s",
            error,
        )

    return None