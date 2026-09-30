from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Comando antiguo deshabilitado. La limpieza física de tablas SQLite con "
        "VACUUM ya no se usa: los datos operativos están en Oracle y db.sqlite3 "
        "es la base `default` de Django, no un residuo que se pueda borrar."
    )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "Este comando está deshabilitado. "
                "Tenía un VACUUM destructivo sobre db.sqlite3, que es la base "
                "default de Django (LogImportacion y demás): no se debe ejecutar."
            )
        )
