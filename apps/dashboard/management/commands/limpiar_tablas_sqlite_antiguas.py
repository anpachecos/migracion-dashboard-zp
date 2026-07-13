import os
import shutil
import sqlite3
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Elimina tablas antiguas del flujo SQLite operativo y ejecuta VACUUM."

    TABLAS_ANTIGUAS_EXACTAS = [
        "dashboard_estadovalidador",
        "dashboard_estadovalidadorraw",
        "dashboard_estadovalidadorlimpio",
        "dashboard_ubicacionesperadavalidador",
        "dashboard_historialubicacionesperadavalidador",
        "dashboard_conversion_fechas_log",
    ]

    PREFIJOS_BACKUP_ANTIGUOS = [
        "dashboard_estadovalidadorlimpio_backup",
        "dashboard_estadovalidadorraw_backup",
        "dashboard_estadovalidador_backup",
        "dashboard_ubicacionesperadavalidador_backup",
        "dashboard_historialubicacionesperadavalidador_backup",
    ]

    TABLAS_PROTEGIDAS = [
        "auth_group",
        "auth_group_permissions",
        "auth_permission",
        "auth_user",
        "auth_user_groups",
        "auth_user_user_permissions",
        "django_admin_log",
        "django_content_type",
        "django_migrations",
        "django_session",
        "dashboard_logimportacion",
        "sqlite_sequence",
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Confirma la eliminación real de tablas antiguas.",
        )

    def handle(self, *args, **options):
        confirmar = options["confirmar"]
        ruta_db = settings.DATABASES["default"]["NAME"]

        if not os.path.exists(ruta_db):
            self.stderr.write(self.style.ERROR(f"No existe la base SQLite: {ruta_db}"))
            return

        tablas_existentes = self.obtener_tablas(ruta_db)
        tablas_a_borrar = self.obtener_tablas_a_borrar(tablas_existentes)

        self.stdout.write(self.style.SUCCESS(f"Base SQLite: {ruta_db}"))
        self.stdout.write("")

        if not tablas_a_borrar:
            self.stdout.write(self.style.SUCCESS("No se encontraron tablas antiguas para borrar."))
            return

        self.stdout.write(self.style.WARNING("Tablas antiguas detectadas:"))

        for tabla in tablas_a_borrar:
            cantidad = self.contar_filas(ruta_db, tabla)
            self.stdout.write(f"- {tabla}: {cantidad} filas")

        self.stdout.write("")

        if not confirmar:
            self.stdout.write(
                self.style.WARNING(
                    "Modo simulación. No se borró nada.\n"
                    "Para borrar realmente, ejecuta:\n"
                    "python manage.py limpiar_tablas_sqlite_antiguas --confirmar"
                )
            )
            return

        ruta_backup = self.crear_backup(ruta_db)
        self.stdout.write(self.style.SUCCESS(f"Backup creado: {ruta_backup}"))

        with sqlite3.connect(ruta_db) as conexion:
            cursor = conexion.cursor()

            for tabla in tablas_a_borrar:
                if tabla in self.TABLAS_PROTEGIDAS:
                    self.stdout.write(
                        self.style.ERROR(f"Saltando tabla protegida: {tabla}")
                    )
                    continue

                self.stdout.write(self.style.WARNING(f"Borrando tabla: {tabla}"))
                cursor.execute(f'DROP TABLE IF EXISTS "{tabla}"')

            conexion.commit()

        self.stdout.write(self.style.WARNING("Ejecutando VACUUM para compactar SQLite..."))

        with sqlite3.connect(ruta_db) as conexion:
            conexion.execute("VACUUM")

        self.stdout.write(self.style.SUCCESS("Limpieza SQLite completada correctamente."))

    def obtener_tablas(self, ruta_db):
        with sqlite3.connect(ruta_db) as conexion:
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                ORDER BY name
            """)
            return [fila[0] for fila in cursor.fetchall()]

    def obtener_tablas_a_borrar(self, tablas_existentes):
        tablas_a_borrar = []

        for tabla in tablas_existentes:
            # Protección extra: nunca borrar logs actuales ni backups de logs.
            if "logimportacion" in tabla.lower():
                continue

            # Protección extra: nunca borrar tablas protegidas.
            if tabla in self.TABLAS_PROTEGIDAS:
                continue

            if tabla in self.TABLAS_ANTIGUAS_EXACTAS:
                tablas_a_borrar.append(tabla)
                continue

            for prefijo in self.PREFIJOS_BACKUP_ANTIGUOS:
                if tabla.startswith(prefijo):
                    tablas_a_borrar.append(tabla)
                    break

        return tablas_a_borrar

    def contar_filas(self, ruta_db, tabla):
        try:
            with sqlite3.connect(ruta_db) as conexion:
                cursor = conexion.cursor()
                cursor.execute(f'SELECT COUNT(*) FROM "{tabla}"')
                return cursor.fetchone()[0]
        except Exception:
            return "No disponible"

    def crear_backup(self, ruta_db):
        carpeta = os.path.dirname(ruta_db)
        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_backup = f"db_backup_antes_limpieza_sqlite_{fecha}.sqlite3"
        ruta_backup = os.path.join(carpeta, nombre_backup)

        shutil.copy2(ruta_db, ruta_backup)

        return ruta_backup