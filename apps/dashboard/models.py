from django.db import models


class EstadoValidador(models.Model):
    amid = models.BigIntegerField()

    fec_descarga = models.DateTimeField(null=True, blank=True)
    fec_estado = models.DateTimeField(null=True, blank=True)

    busid = models.IntegerField(null=True, blank=True)
    op = models.IntegerField(null=True, blank=True)

    version = models.CharField(max_length=50, null=True, blank=True)
    patente = models.CharField(max_length=50, null=True, blank=True)

    td01 = models.IntegerField(null=True, blank=True)
    td04 = models.IntegerField(null=True, blank=True)

    tabla = models.IntegerField(null=True, blank=True)
    ver_tabla = models.CharField(max_length=50, null=True, blank=True)
    fecha_hora = models.DateTimeField(null=True, blank=True)

    is_contiene_bateria = models.BooleanField(null=True, blank=True)
    is_contiene_gps = models.BooleanField(null=True, blank=True)
    is_contiene_tiempo_vida = models.BooleanField(null=True, blank=True)

    is_error_obtener_bateria = models.BooleanField(null=True, blank=True)
    is_error_obtener_gps = models.BooleanField(null=True, blank=True)
    is_error_obtener_tiempo_vida = models.BooleanField(null=True, blank=True)

    latitud = models.DecimalField(max_digits=15, decimal_places=10, null=True, blank=True)
    longitud = models.DecimalField(max_digits=15, decimal_places=10, null=True, blank=True)
    porcentaje_bateria = models.IntegerField(null=True, blank=True)

    tiempo_vida = models.DateTimeField(null=True, blank=True)
    fecha_registro = models.DateTimeField(null=True, blank=True)

    fecha_importacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["amid"]),
            models.Index(fields=["fecha_hora"]),
            models.Index(fields=["porcentaje_bateria"]),
        ]

    def __str__(self):
        return f"{self.amid} - {self.porcentaje_bateria}"

class LogImportacion(models.Model):
    ORIGEN_CHOICES = [
        ("CSV", "CSV"),
        ("ORACLE", "Oracle"),
        ("LIMPIEZA", "Limpieza"),

    ]

    ESTADO_CHOICES = [
        ("OK", "OK"),
        ("ERROR", "Error"),
    ]

    origen = models.CharField(max_length=20, choices=ORIGEN_CHOICES)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES)

    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField(null=True, blank=True)

    filas_obtenidas = models.IntegerField(default=0)
    filas_creadas = models.IntegerField(default=0)
    filas_eliminadas = models.IntegerField(default=0)

    mensaje = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.origen} - {self.estado} - {self.fecha_inicio}"
    
#Datos directos de Oracle
class EstadoValidadorRaw(models.Model):
    amid = models.BigIntegerField()

    fec_descarga = models.DateTimeField(null=True, blank=True)
    fec_estado = models.DateTimeField(null=True, blank=True)

    busid = models.IntegerField(null=True, blank=True)
    op = models.IntegerField(null=True, blank=True)

    version = models.CharField(max_length=50, null=True, blank=True)
    patente = models.CharField(max_length=50, null=True, blank=True)

    td01 = models.IntegerField(null=True, blank=True)
    td04 = models.IntegerField(null=True, blank=True)

    tabla = models.IntegerField(null=True, blank=True)
    ver_tabla = models.CharField(max_length=50, null=True, blank=True)
    fecha_hora = models.DateTimeField(null=True, blank=True)

    is_contiene_bateria = models.BooleanField(null=True, blank=True)
    is_contiene_gps = models.BooleanField(null=True, blank=True)
    is_contiene_tiempo_vida = models.BooleanField(null=True, blank=True)

    is_error_obtener_bateria = models.BooleanField(null=True, blank=True)
    is_error_obtener_gps = models.BooleanField(null=True, blank=True)
    is_error_obtener_tiempo_vida = models.BooleanField(null=True, blank=True)

    latitud = models.DecimalField(max_digits=15, decimal_places=10, null=True, blank=True)
    longitud = models.DecimalField(max_digits=15, decimal_places=10, null=True, blank=True)
    porcentaje_bateria = models.IntegerField(null=True, blank=True)

    tiempo_vida = models.DateTimeField(null=True, blank=True)
    fecha_registro = models.DateTimeField(null=True, blank=True)

    fecha_importacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["amid", "fecha_hora"],
                name="unique_raw_amid_fecha_hora"
            )
        ]
        indexes = [
            models.Index(fields=["amid"]),
            models.Index(fields=["fecha_hora"]),
            models.Index(fields=["porcentaje_bateria"]),
        ]

    def __str__(self):
        return f"RAW {self.amid} - {self.fecha_hora}"

#Datos limpios y validados para análisis y visualización
class EstadoValidadorLimpio(models.Model):
    amid = models.BigIntegerField()

    fec_descarga = models.DateTimeField(null=True, blank=True)
    fec_estado = models.DateTimeField(null=True, blank=True)

    busid = models.IntegerField(null=True, blank=True)
    op = models.IntegerField(null=True, blank=True)

    version = models.CharField(max_length=50, null=True, blank=True)
    patente = models.CharField(max_length=50, null=True, blank=True)

    td01 = models.IntegerField(null=True, blank=True)
    td04 = models.IntegerField(null=True, blank=True)

    tabla = models.IntegerField(null=True, blank=True)
    ver_tabla = models.CharField(max_length=50, null=True, blank=True)
    fecha_hora = models.DateTimeField(null=True, blank=True)

    is_contiene_bateria = models.BooleanField(null=True, blank=True)
    is_contiene_gps = models.BooleanField(null=True, blank=True)
    is_contiene_tiempo_vida = models.BooleanField(null=True, blank=True)

    is_error_obtener_bateria = models.BooleanField(null=True, blank=True)
    is_error_obtener_gps = models.BooleanField(null=True, blank=True)
    is_error_obtener_tiempo_vida = models.BooleanField(null=True, blank=True)

    latitud = models.DecimalField(max_digits=15, decimal_places=10, null=True, blank=True)
    longitud = models.DecimalField(max_digits=15, decimal_places=10, null=True, blank=True)
    porcentaje_bateria = models.IntegerField(null=True, blank=True)

    tiempo_vida = models.DateTimeField(null=True, blank=True)
    fecha_registro = models.DateTimeField(null=True, blank=True)

    fecha_importacion = models.DateTimeField(null=True, blank=True)
    fecha_limpieza = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["amid", "fecha_hora"],
                name="unique_limpio_amid_fecha_hora"
            )
        ]
        indexes = [
            models.Index(fields=["amid"]),
            models.Index(fields=["fecha_hora"]),
            models.Index(fields=["porcentaje_bateria"]),
        ]

    def __str__(self):
        return f"LIMPIO {self.amid} - {self.fecha_hora}"