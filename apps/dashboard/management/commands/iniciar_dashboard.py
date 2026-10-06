import os
import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Inicia el servidor web, el worker de archivos y el scheduler."

    def add_arguments(self, parser):
        parser.add_argument(
            "--modo",
            choices=("development", "production"),
            default=os.getenv("DASHBOARD_LAUNCHER_MODE", "development"),
        )
        parser.add_argument("--host", default=os.getenv("DASHBOARD_WEB_HOST", "127.0.0.1"))
        parser.add_argument("--port", default=os.getenv("DASHBOARD_WEB_PORT", "8000"))

    def handle(self, *args, **options):
        log_dir = Path(settings.DASHBOARD_LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        modo = options["modo"]
        entorno = os.environ.copy()
        # The scheduler is owned by its child process, never by the web child.
        entorno["DASHBOARD_SCHEDULER_EMBEDDED"] = "False"

        comandos = self._comandos(modo, options["host"], options["port"])
        procesos = []
        archivos = []

        try:
            for nombre, comando in comandos:
                ruta_log = log_dir / f"{nombre}.log"
                archivo = ruta_log.open("a", encoding="utf-8", buffering=1)
                archivos.append(archivo)
                self._registrar_launcher(log_dir, f"Iniciando {nombre}: {' '.join(comando)}")
                proceso = subprocess.Popen(
                    comando,
                    cwd=str(settings.BASE_DIR),
                    env=entorno,
                    stdout=archivo,
                    stderr=subprocess.STDOUT,
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                    ),
                )
                procesos.append((nombre, proceso))

            self.stdout.write(
                self.style.SUCCESS(
                    "Dashboard iniciado. Web, worker y scheduler están activos."
                )
            )
            self.stdout.write(f"Logs: {log_dir}")

            while True:
                for nombre, proceso in procesos:
                    codigo = proceso.poll()
                    if codigo is not None:
                        raise CommandError(
                            f"El proceso {nombre} terminó inesperadamente con código {codigo}."
                        )
                time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write("Deteniendo dashboard...")
        finally:
            self._detener_procesos(procesos)
            for archivo in archivos:
                archivo.close()

    def _comandos(self, modo, host, port):
        python = sys.executable
        if modo == "production":
            web = [
                python,
                "-m",
                "waitress",
                f"--listen={host}:{port}",
                "config.wsgi:application",
            ]
        else:
            web = [
                python,
                "manage.py",
                "runserver",
                f"{host}:{port}",
                "--noreload",
            ]

        return [
            ("web", web),
            ("worker", [python, "manage.py", "procesar_trabajos"]),
            ("scheduler", [python, "manage.py", "ejecutar_scheduler"]),
        ]

    def _registrar_launcher(self, log_dir, mensaje):
        with (Path(log_dir) / "launcher.log").open(
            "a", encoding="utf-8", buffering=1
        ) as archivo:
            archivo.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {mensaje}\n")

    def _detener_procesos(self, procesos):
        if os.name == "nt":
            for _, proceso in reversed(procesos):
                if proceso.poll() is None:
                    subprocess.run(
                        ["taskkill", "/PID", str(proceso.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
        else:
            for _, proceso in reversed(procesos):
                if proceso.poll() is None:
                    proceso.terminate()

        limite = time.time() + 10
        for nombre, proceso in reversed(procesos):
            if proceso.poll() is None:
                restante = max(0, limite - time.time())
                try:
                    proceso.wait(timeout=restante)
                except subprocess.TimeoutExpired:
                    proceso.kill()
                    self._registrar_launcher(
                        settings.DASHBOARD_LOG_DIR,
                        f"Proceso {nombre} terminó forzosamente.",
                    )
