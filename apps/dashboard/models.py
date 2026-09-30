from django.conf import settings
from django.db import models


class LogImportacion(models.Model):
    """
    Modelo local usado para registrar procesos internos del dashboard.

    Esta tabla vive en SQLite y se usa para guardar eventos como:
    - pruebas de conexión Oracle;
    - importación de ubicaciones esperadas;
    - exportaciones Excel;
    - ejecución del scheduler;
    - estado general de Oracle;
    - errores o advertencias del sistema.
    """

    ORIGEN_CHOICES = [
        ("PROBAR_ORACLE", "Probar conexión Oracle"),
        ("UBICACIONES_ORACLE", "Ubicaciones esperadas Oracle"),
        ("BATERIA_BLOQUES_ORACLE", "Batería bloques Oracle"),
        ("ESTADO_ORACLE", "Estado general Oracle"),
        ("EXPORT_EXCEL", "Exportación Excel"),
        ("SCHEDULER", "Scheduler"),
        ("SISTEMA", "Sistema"),

        # Orígenes antiguos.
        # Se mantienen para no romper logs históricos ya guardados en SQLite.
        ("CSV", "CSV"),
        ("ORACLE", "Oracle antiguo"),
        ("LIMPIEZA", "Limpieza antigua"),
        ("EXCEL_UBICACIONES", "Excel ubicaciones antiguo"),
    ]

    ESTADO_CHOICES = [
        ("OK", "OK"),
        ("ERROR", "Error"),
        ("ADVERTENCIA", "Advertencia"),
        ("INFO", "Información"),
    ]

    origen = models.CharField(
        max_length=50,
        choices=ORIGEN_CHOICES,
        help_text="Proceso que generó el log.",
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        help_text="Resultado del proceso.",
    )

    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField(null=True, blank=True)

    filas_obtenidas = models.IntegerField(default=0)
    filas_creadas = models.IntegerField(default=0)
    filas_eliminadas = models.IntegerField(default=0)

    mensaje = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["origen"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["fecha_inicio"]),
            models.Index(fields=["origen", "fecha_inicio"]),
        ]
        verbose_name = "Log de importación"
        verbose_name_plural = "Logs de importación"

    def __str__(self):
        return f"{self.origen} - {self.estado} - {self.fecha_inicio}"

class AlertaAmidExcluido(models.Model):
    """AMID que un usuario decidi\u00f3 ocultar del panel de alertas."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alertas_amids_excluidos",
    )
    amid = models.BigIntegerField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["amid"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "amid"],
                name="uq_alerta_usuario_amid",
            ),
        ]
        verbose_name = "AMID excluido del panel de alertas"
        verbose_name_plural = "AMID excluidos del panel de alertas"

    def __str__(self):
        return f"{self.usuario} - AMID {self.amid}"


class AlertaUbicacionExcluida(models.Model):
    """Ubicaci\u00f3n cuyos AMID un usuario decidi\u00f3 ocultar del panel."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alertas_ubicaciones_excluidas",
    )
    nombre = models.CharField(max_length=255)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "nombre"],
                name="uq_alerta_usuario_ubicacion",
            ),
        ]
        verbose_name = "Ubicaci\u00f3n excluida del panel de alertas"
        verbose_name_plural = "Ubicaciones excluidas del panel de alertas"

    def __str__(self):
        return f"{self.usuario} - {self.nombre}"
