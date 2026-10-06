import time
import logging
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.dashboard.services.trabajos import (
    marcar_interrumpidos,
    procesar_trabajo,
    tomar_siguiente_trabajo,
)


class Command(BaseCommand):
    help = "Procesa secuencialmente los trabajos de archivos pendientes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--una-vez",
            action="store_true",
            help="Procesa como máximo un trabajo y termina.",
        )
        parser.add_argument(
            "--sin-espera",
            action="store_true",
            help="Termina cuando no quedan trabajos pendientes.",
        )

    def handle(self, *args, **options):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            stream=sys.stdout,
            force=True,
        )
        interrumpidos = marcar_interrumpidos()
        if interrumpidos:
            self.stdout.write(
                self.style.WARNING(
                    f"Se marcaron {interrumpidos} trabajo(s) interrumpido(s) como ERROR."
                )
            )

        while True:
            close_old_connections()
            trabajo = tomar_siguiente_trabajo()
            if trabajo is None:
                if options["una_vez"] or options["sin_espera"]:
                    return
                time.sleep(settings.TRABAJOS_WORKER_INTERVALO_SEGUNDOS)
                continue

            self.stdout.write(
                f"Trabajo #{trabajo.pk}: iniciado ({trabajo.tipo})."
            )
            procesar_trabajo(trabajo)
            self.stdout.write(
                f"Trabajo #{trabajo.pk}: finalizado como {trabajo.estado.lower()}."
            )
            if options["una_vez"]:
                return
