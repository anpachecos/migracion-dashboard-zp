from django.contrib import admin

from .models import TrabajoArchivo


@admin.register(TrabajoArchivo)
class TrabajoArchivoAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario", "tipo", "estado", "fecha_solicitud", "leido")
    list_filter = ("estado", "tipo", "leido")
    search_fields = ("usuario__username", "nombre_archivo", "error")
    readonly_fields = (
        "fecha_solicitud",
        "fecha_inicio",
        "fecha_fin",
        "archivo_entrada",
        "archivo",
    )
