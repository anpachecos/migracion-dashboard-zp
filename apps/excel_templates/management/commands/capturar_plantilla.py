from django.core.management.base import BaseCommand, CommandError

from apps.excel_templates import services


class Command(BaseCommand):
    help = (
        "Captura un archivo .xlsx o .xlsm como plantilla del motor de "
        "formatos. Es la misma operacion que hara la Fase 2 desde la web: "
        "extrae el formato, lo guarda en SQLite y deja una version nueva."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "archivo",
            help="Ruta del .xlsx o .xlsm a capturar.",
        )
        parser.add_argument(
            "--name",
            "--nombre",
            dest="name",
            required=True,
            help="Nombre de la plantilla. Es el texto que ve el usuario.",
        )
        parser.add_argument(
            "--description",
            "--descripcion",
            dest="description",
            default="",
            help="Descripcion de la plantilla.",
        )
        parser.add_argument(
            "--notes",
            "--notas",
            dest="notes",
            default="",
            help="Notas de la version (por que se capturo).",
        )
        parser.add_argument(
            "--created-by",
            "--creado-por",
            dest="created_by",
            default="manage",
            help="Quien hizo la captura. Va al log.",
        )
        parser.add_argument(
            "--no-publicar",
            action="store_true",
            help="Deja la version en BORRADOR sin cambiar la vigente.",
        )
        parser.add_argument(
            "--export",
            dest="exportar",
            default="",
            help="Ruta donde escribir tambien la plantilla vacia generada.",
        )

    def handle(self, *args, **opciones):
        archivo = opciones["archivo"]

        try:
            resultado = services.capturar(
                archivo,
                nombre=opciones["name"],
                descripcion=opciones["description"],
                notas=opciones["notes"],
                creado_por=opciones["created_by"],
                publicar=not opciones["no_publicar"],
            )
        except FileNotFoundError:
            raise CommandError(f"No existe el archivo: {archivo}")
        except services.ErrorDePlantilla as error:
            raise CommandError(str(error))

        version = resultado["version"]
        plantilla = resultado["plantilla"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Plantilla '{plantilla.name}' v{version.version_no} "
                f"({'nueva' if resultado['creada'] else 'actualizada'})."
            )
        )
        self.stdout.write(f"  Origen:   {version.source_filename}")
        self.stdout.write(f"  SHA-256:  {version.source_sha256}")
        self.stdout.write(f"  Exporta:  {plantilla.export_filename}")
        self.stdout.write(f"  Guardado: {resultado['resultado']}")

        _mostrar_reporte(self, resultado.get("reporte"))

        if opciones["exportar"]:
            from apps.excel_templates.options import ExportOptions

            exportado = services.exportar(plantilla, opciones=ExportOptions())
            with open(opciones["exportar"], "wb") as destino:
                destino.write(exportado["datos"])
            self.stdout.write(
                self.style.SUCCESS(f"Plantilla vacia escrita en {opciones['exportar']}")
            )
            _mostrar_reporte(self, exportado["reporte"].como_dict())


def _mostrar_reporte(comando, reporte):
    """Imprime el reporte de lo no soportado, que nunca se descarta en silencio."""

    if not reporte or not reporte.get("entradas"):
        return

    entradas = reporte["entradas"]
    resumen = {}
    for entrada in entradas:
        resumen[entrada["nivel"]] = resumen.get(entrada["nivel"], 0) + 1

    comando.stdout.write(
        comando.style.WARNING("  Reporte: " + ", ".join(
            f"{nivel}={conteo}" for nivel, conteo in sorted(resumen.items())
        ))
    )

    for entrada in entradas:
        if entrada["nivel"] == "soportado":
            continue
        hoja = f" [{entrada['sheet']}]" if entrada.get("sheet") else ""
        comando.stdout.write(
            f"    - {entrada['nivel']}: {entrada['feature']}{hoja}: "
            f"{entrada['detalle']}"
        )