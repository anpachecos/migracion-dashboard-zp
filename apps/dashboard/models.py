from django.db import models


class LogImportacion(models.Model):
    ORIGEN_CHOICES = [
        ("PROBAR_ORACLE", "Probar conexión Oracle"),
        ("UBICACIONES_ORACLE", "Ubicaciones esperadas Oracle"),
        ("BATERIA_BLOQUES_ORACLE", "Batería bloques Oracle"),
        ("ESTADO_ORACLE", "Estado general Oracle"),
        ("EXPORT_EXCEL", "Exportación Excel"),
        ("SCHEDULER", "Scheduler"),
        ("SISTEMA", "Sistema"),

        # Orígenes antiguos, se mantienen para no romper logs históricos.
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


class EstatusZP(models.Model):
    """
    Modelo de solo lectura sobre la vista Oracle USR_LAB.VW_ESTATUS_ZP_DJANGO.

    No es una tabla SQLite.
    No se administra con migraciones Django porque managed = False.
    """

    id = models.CharField(db_column="ID", max_length=50, primary_key=True)

    amid = models.BigIntegerField(db_column="AMID")

    fec_descarga = models.DateTimeField(
        db_column="FEC_DESCARGA",
        null=True,
        blank=True,
    )
    fec_estado = models.DateTimeField(
        db_column="FEC_ESTADO",
        null=True,
        blank=True,
    )

    busid = models.IntegerField(
        db_column="BUSID",
        null=True,
        blank=True,
    )
    op = models.IntegerField(
        db_column="OP",
        null=True,
        blank=True,
    )

    version = models.CharField(
        db_column="VERSION",
        max_length=50,
        null=True,
        blank=True,
    )
    patente = models.CharField(
        db_column="PATENTE",
        max_length=50,
        null=True,
        blank=True,
    )

    td01 = models.IntegerField(
        db_column="TD01",
        null=True,
        blank=True,
    )
    td04 = models.IntegerField(
        db_column="TD04",
        null=True,
        blank=True,
    )

    tabla = models.IntegerField(
        db_column="TABLA",
        null=True,
        blank=True,
    )
    ver_tabla = models.CharField(
        db_column="VER_TABLA",
        max_length=50,
        null=True,
        blank=True,
    )

    fecha_hora = models.DateTimeField(
        db_column="FECHA_HORA",
        null=True,
        blank=True,
    )

    is_contiene_bateria = models.BooleanField(
        db_column="IS_CONTIENE_BATERIA",
        null=True,
        blank=True,
    )
    is_contiene_gps = models.BooleanField(
        db_column="IS_CONTIENE_GPS",
        null=True,
        blank=True,
    )
    is_contiene_tiempo_vida = models.BooleanField(
        db_column="IS_CONTIENE_TIEMPO_VIDA",
        null=True,
        blank=True,
    )

    is_error_obtener_bateria = models.BooleanField(
        db_column="IS_ERROR_OBTENER_BATERIA",
        null=True,
        blank=True,
    )
    is_error_obtener_gps = models.BooleanField(
        db_column="IS_ERROR_OBTENER_GPS",
        null=True,
        blank=True,
    )
    is_error_obtener_tiempo_vida = models.BooleanField(
        db_column="IS_ERROR_OBTENER_TIEMPO_VIDA",
        null=True,
        blank=True,
    )

    latitud = models.DecimalField(
        db_column="LATITUD",
        max_digits=20,
        decimal_places=10,
        null=True,
        blank=True,
    )
    longitud = models.DecimalField(
        db_column="LONGITUD",
        max_digits=20,
        decimal_places=10,
        null=True,
        blank=True,
    )

    porcentaje_bateria = models.IntegerField(
        db_column="PORCENTAJE_BATERIA",
        null=True,
        blank=True,
    )

    tiempo_vida = models.DateTimeField(
        db_column="TIEMPO_VIDA",
        null=True,
        blank=True,
    )
    fecha_registro = models.DateTimeField(
        db_column="FECHA_REGISTRO",
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "VW_ESTATUS_ZP_DJANGO"

    def __str__(self):
        return f"{self.amid} - {self.fecha_hora} - {self.porcentaje_bateria}"