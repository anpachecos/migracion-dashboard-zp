import logging
import sys
import time

from django.core.management.base import BaseCommand

from apps.dashboard import scheduler


class Command(BaseCommand):
    help = "Ejecuta el scheduler Oracle como proceso independiente."

    def handle(self, *args, **options):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            stream=sys.stdout,
            force=True,
        )

        scheduler.iniciar_scheduler()
        self.stdout.write(self.style.SUCCESS("Scheduler independiente iniciado."))

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write("Deteniendo scheduler independiente.")
            if scheduler.scheduler.running:
                scheduler.scheduler.shutdown(wait=False)
