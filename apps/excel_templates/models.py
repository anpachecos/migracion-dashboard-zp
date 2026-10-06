"""
Modelos del motor de plantillas Excel (Fase 1: solo formato).

La idea central es que un `.xlsx` se capture una vez como *formato* y desde
entonces la web exporte plantillas vacias de datos pero identicas en formato.
Para que eso sea viable con archivos grandes, el estilo se guarda:

- **deduplicado** en tablas por componente (fuente, relleno, borde,
  alineacion, proteccion, formato numerico) con un `hash` unico, y
- **aplicado por tramos** (`xl_cell_style_run`): celdas contiguas de una misma
  fila con el mismo estilo son un solo registro. Sin esto, una hoja que
  declara un millon de filas con estilo no cabe en memoria ni en la base.

Ningun dato del Excel original se guarda aqui salvo el texto de las celdas
marcadas como `HEADER` o `LEGEND` en `xl_cell_label`, porque sin las cabeceras
la plantilla no sirve.

Los nombres de tabla llevan el prefijo `xl_` y las tablas cuelgan de
`xl_template_version` con `ON DELETE CASCADE`: cada version es inmutable y el
historial se conserva al "sobrescribir" una plantilla (Fase 2).
"""

from django.db import models


class Template(models.Model):
    """Plantilla Excel. Es el nombre que ve el usuario en el selector."""

    name = models.CharField(max_length=255, unique=True)
    export_filename = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    #: Puntero a la version vigente. Es lo unico que define cual es "la"
    #: plantilla actual: hacer rollback es mover este puntero, sin borrar el
    #: historial de versiones.
    current_version = models.ForeignKey(
        "excel_templates.TemplateVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "xl_template"
        verbose_name = "Plantilla Excel"
        verbose_name_plural = "Plantillas Excel"
        ordering = ["name"]

    def __str__(self):
        return self.name


class TemplateVersion(models.Model):
    """
    Version inmutable de una plantilla.

    "Sobrescribir" una plantilla no edita la version vigente: crea una nueva y
    mueve `Template.current_version`. Asi el rollback es cambiar ese puntero, y
    `source_sha256` permite detectar que un Excel ya fue importado.
    """

    class Status(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        VIGENTE = "VIGENTE", "Vigente"
        ARCHIVADA = "ARCHIVADA", "Archivada"

    template = models.ForeignKey(
        Template,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_no = models.PositiveIntegerField()
    source_filename = models.CharField(max_length=255)
    source_ext = models.CharField(max_length=10, default=".xlsx")
    source_sha256 = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.BORRADOR,
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "xl_template_version"
        verbose_name = "Version de plantilla Excel"
        verbose_name_plural = "Versiones de plantilla Excel"
        ordering = ["-version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "version_no"],
                name="uq_xl_version_template_numero",
            ),
        ]
        indexes = [
            models.Index(fields=["template", "-version_no"], name="ix_xl_version_template"),
            models.Index(fields=["source_sha256"], name="ix_xl_version_sha256"),
        ]

    def __str__(self):
        return f"{self.template.name} v{self.version_no}"


class WorkbookMeta(models.Model):
    """Metadatos del libro entero, guardados por version."""

    version = models.OneToOneField(
        TemplateVersion,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="meta",
    )
    theme_xml = models.TextField(blank=True, default="")
    defined_names_json = models.JSONField(blank=True, null=True)
    workbook_props_json = models.JSONField(blank=True, null=True)
    calc_props_json = models.JSONField(blank=True, null=True)
    extra_json = models.JSONField(blank=True, null=True)

    class Meta:
        db_table = "xl_workbook_meta"
        verbose_name = "Metadatos del libro"
        verbose_name_plural = "Metadatos de libros"


class Font(models.Model):
    hash = models.CharField(max_length=64, unique=True)
    data_json = models.JSONField()

    class Meta:
        db_table = "xl_font"
        ordering = ["hash"]


class Fill(models.Model):
    hash = models.CharField(max_length=64, unique=True)
    data_json = models.JSONField()

    class Meta:
        db_table = "xl_fill"
        ordering = ["hash"]


class Border(models.Model):
    hash = models.CharField(max_length=64, unique=True)
    data_json = models.JSONField()

    class Meta:
        db_table = "xl_border"
        ordering = ["hash"]


class Alignment(models.Model):
    hash = models.CharField(max_length=64, unique=True)
    data_json = models.JSONField()

    class Meta:
        db_table = "xl_alignment"
        ordering = ["hash"]


class Protection(models.Model):
    hash = models.CharField(max_length=64, unique=True)
    data_json = models.JSONField()

    class Meta:
        db_table = "xl_protection"
        ordering = ["hash"]


class NumberFormat(models.Model):
    hash = models.CharField(max_length=64, unique=True)
    data_json = models.JSONField()

    class Meta:
        db_table = "xl_number_format"
        ordering = ["hash"]


class Style(models.Model):
    """Combinacion de los componentes anteriores, deduplicada por hash."""

    hash = models.CharField(max_length=64, unique=True)
    font = models.ForeignKey(
        Font, on_delete=models.PROTECT, related_name="styles"
    )
    fill = models.ForeignKey(
        Fill, on_delete=models.PROTECT, related_name="styles"
    )
    border = models.ForeignKey(
        Border, on_delete=models.PROTECT, related_name="styles"
    )
    alignment = models.ForeignKey(
        Alignment, on_delete=models.PROTECT, related_name="styles"
    )
    protection = models.ForeignKey(
        Protection, on_delete=models.PROTECT, related_name="styles"
    )
    number_format = models.ForeignKey(
        NumberFormat, on_delete=models.PROTECT, related_name="styles"
    )

    class Meta:
        db_table = "xl_style"
        ordering = ["hash"]


class Dxf(models.Model):
    """Estilo diferencial usado por las reglas de formato condicional."""

    hash = models.CharField(max_length=64, unique=True)
    data_json = models.JSONField()

    class Meta:
        db_table = "xl_dxf"
        ordering = ["hash"]


class Sheet(models.Model):
    class State(models.TextChoices):
        VISIBLE = "VISIBLE", "Visible"
        HIDDEN = "HIDDEN", "Oculta"
        VERY_HIDDEN = "VERY_HIDDEN", "Muy oculta"

    version = models.ForeignKey(
        TemplateVersion,
        on_delete=models.CASCADE,
        related_name="sheets",
    )
    position = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.VISIBLE
    )
    tab_color_json = models.JSONField(blank=True, null=True)
    default_row_height = models.FloatField(blank=True, null=True)
    default_col_width = models.FloatField(blank=True, null=True)
    sheet_view_json = models.JSONField(blank=True, null=True)
    page_setup_json = models.JSONField(blank=True, null=True)
    margins_json = models.JSONField(blank=True, null=True)
    print_json = models.JSONField(blank=True, null=True)
    header_footer_json = models.JSONField(blank=True, null=True)
    extra_json = models.JSONField(blank=True, null=True)

    class Meta:
        db_table = "xl_sheet"
        verbose_name = "Hoja de plantilla"
        verbose_name_plural = "Hojas de plantilla"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "position"],
                name="uq_xl_sheet_version_posicion",
            ),
        ]

    def __str__(self):
        return f"{self.position}: {self.name}"


class Column(models.Model):
    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name="columns")
    min_idx = models.PositiveIntegerField()
    max_idx = models.PositiveIntegerField()
    width = models.FloatField(blank=True, null=True)
    hidden = models.BooleanField(default=False)
    best_fit = models.BooleanField(default=False)
    outline_level = models.PositiveIntegerField(default=0)
    style = models.ForeignKey(
        Style, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        db_table = "xl_column"
        ordering = ["min_idx", "max_idx"]
        constraints = [
            models.UniqueConstraint(
                fields=["sheet", "min_idx", "max_idx"],
                name="uq_xl_column_rango",
            ),
        ]


class Row(models.Model):
    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name="rows")
    row_idx = models.PositiveIntegerField()
    height = models.FloatField(blank=True, null=True)
    hidden = models.BooleanField(default=False)
    outline_level = models.PositiveIntegerField(default=0)
    style = models.ForeignKey(
        Style, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        db_table = "xl_row"
        ordering = ["row_idx"]
        constraints = [
            models.UniqueConstraint(
                fields=["sheet", "row_idx"],
                name="uq_xl_row_sheet_indice",
            ),
        ]
        indexes = [
            models.Index(fields=["sheet", "row_idx"], name="ix_xl_row_sheet_indice"),
        ]


class CellStyleRun(models.Model):
    """
    Estilo por tramos: celdas contiguas de una fila con el mismo estilo.

    `role` decide si el texto de esas celdas se conserva al exportar
    (`HEADER`/`LEGEND`) o se vacia (`DATA`). Es editable para que el usuario
    corrija la heuristica sin reimportar el Excel.
    """

    class Role(models.TextChoices):
        HEADER = "HEADER", "Cabecera"
        LEGEND = "LEGEND", "Leyenda"
        DATA = "DATA", "Dato"
        UNKNOWN = "UNKNOWN", "Desconocido"

    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name="style_runs")
    row_idx = models.PositiveIntegerField()
    col_start = models.PositiveIntegerField()
    col_end = models.PositiveIntegerField()
    style = models.ForeignKey(Style, on_delete=models.PROTECT)
    role = models.CharField(
        max_length=16, choices=Role.choices, default=Role.DATA
    )

    class Meta:
        db_table = "xl_cell_style_run"
        ordering = ["sheet_id", "row_idx", "col_start"]
        indexes = [
            models.Index(fields=["sheet", "row_idx"], name="ix_xl_run_sheet_fila"),
        ]


class CellLabel(models.Model):
    """Unico lugar donde puede quedar texto del Excel original."""

    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name="labels")
    row_idx = models.PositiveIntegerField()
    col_idx = models.PositiveIntegerField()
    value = models.TextField(blank=True, default="")
    value_type = models.CharField(max_length=16, default="s")

    class Meta:
        db_table = "xl_cell_label"
        ordering = ["sheet_id", "row_idx", "col_idx"]
        constraints = [
            models.UniqueConstraint(
                fields=["sheet", "row_idx", "col_idx"],
                name="uq_xl_label_celda",
            ),
        ]


class MergedRange(models.Model):
    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name="merged")
    ref = models.CharField(max_length=64)

    class Meta:
        db_table = "xl_merged_range"
        ordering = ["ref"]
        constraints = [
            models.UniqueConstraint(fields=["sheet", "ref"], name="uq_xl_merged_ref"),
        ]


class DataValidation(models.Model):
    sheet = models.ForeignKey(
        Sheet, on_delete=models.CASCADE, related_name="data_validations"
    )
    sqref_json = models.JSONField()
    type = models.CharField(max_length=32, blank=True, default="")
    formula1_json = models.JSONField(blank=True, null=True)
    formula2_json = models.JSONField(blank=True, null=True)
    options_json = models.JSONField(blank=True, null=True)

    class Meta:
        db_table = "xl_data_validation"


class ConditionalFormat(models.Model):
    """
    Regla de formato condicional.

    `sqref_json` es la lista completa de rangos tal como la escribe Excel
    (`["Y2:Y24", "Y26:Y29", ...]`): las reglas llegan fragmentadas y perder un
    rango cambia el comportamiento en pantalla.
    """

    sheet = models.ForeignKey(
        Sheet, on_delete=models.CASCADE, related_name="conditional_formats"
    )
    sqref_json = models.JSONField()
    type = models.CharField(max_length=32)
    operator = models.CharField(max_length=32, blank=True, default="")
    priority = models.IntegerField(default=1)
    stop_if_true = models.BooleanField(default=False)
    text = models.TextField(blank=True, default="")
    time_period = models.CharField(max_length=16, blank=True, default="")
    rank = models.IntegerField(blank=True, null=True)
    percent = models.BooleanField(blank=True, null=True)
    bottom = models.BooleanField(blank=True, null=True)
    std_dev = models.IntegerField(blank=True, null=True)
    above_average = models.BooleanField(blank=True, null=True)
    equal_average = models.BooleanField(blank=True, null=True)
    formulas_json = models.JSONField(blank=True, null=True)
    color_scale_json = models.JSONField(blank=True, null=True)
    data_bar_json = models.JSONField(blank=True, null=True)
    icon_set_json = models.JSONField(blank=True, null=True)
    dxf = models.ForeignKey(Dxf, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "xl_conditional_format"
        ordering = ["sheet_id", "priority"]


class Autofilter(models.Model):
    """
    Autofiltro con sus criterios activos.

    `hidden_rows_json` guarda las filas que el archivo traia ocultas y
    `columns_json` los `filterColumn` (valores, filtros personalizados, de
    color, dinamicos). Se guardan aunque aplicarlos por completo sea una etapa
    posterior: la informacion no se pierde.
    """

    sheet = models.OneToOneField(
        Sheet, on_delete=models.CASCADE, related_name="autofilter"
    )
    ref = models.CharField(max_length=64, blank=True, default="")
    columns_json = models.JSONField(blank=True, null=True)
    sort_state_json = models.JSONField(blank=True, null=True)
    hidden_rows_json = models.JSONField(blank=True, null=True)

    class Meta:
        db_table = "xl_autofilter"


class Table(models.Model):
    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name="tables")
    name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True, default="")
    ref = models.CharField(max_length=64, blank=True, default="")
    table_json = models.JSONField(blank=True, null=True)

    class Meta:
        db_table = "xl_table"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["sheet", "name"], name="uq_xl_table_nombre"),
        ]


class CommentShell(models.Model):
    """
    Caja de comentario sin su texto.

    El texto del comentario es contenido, no formato, asi que se guarda aparte
    (`text_json`, vacio por defecto) y por defecto no se exporta. Si el archivo
    tiene comentarios de plantilla fijos, Fase 2 podra marcarlos para
    conservarlos.
    """

    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name="comments")
    cell_ref = models.CharField(max_length=16)
    author = models.CharField(max_length=255, blank=True, default="")
    from_col = models.PositiveIntegerField(blank=True, null=True)
    from_row = models.PositiveIntegerField(blank=True, null=True)
    from_col_off = models.IntegerField(blank=True, null=True)
    from_row_off = models.IntegerField(blank=True, null=True)
    to_col = models.PositiveIntegerField(blank=True, null=True)
    to_row = models.PositiveIntegerField(blank=True, null=True)
    to_col_off = models.IntegerField(blank=True, null=True)
    to_row_off = models.IntegerField(blank=True, null=True)
    text_json = models.TextField(blank=True, default="")
    width = models.FloatField(blank=True, null=True)
    height = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = "xl_comment_shell"
        ordering = ["cell_ref"]
        constraints = [
            models.UniqueConstraint(
                fields=["sheet", "cell_ref"], name="uq_xl_comment_celda"
            ),
        ]


class ImageRef(models.Model):
    """Imagen/logo del libro. Fase 1 la registra; el binario no se guarda."""

    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name="images")
    anchor_json = models.JSONField(blank=True, null=True)
    media_name = models.CharField(max_length=255, blank=True, default="")
    media_sha256 = models.CharField(max_length=64, blank=True, default="")
    media_ext = models.CharField(max_length=16, blank=True, default="")

    class Meta:
        db_table = "xl_image_ref"


class PrintTitle(models.Model):
    """Titulos de impresion repetidos (`print_title_rows` / `_cols`)."""

    sheet = models.OneToOneField(
        Sheet, on_delete=models.CASCADE, related_name="print_title"
    )
    rows = models.CharField(max_length=64, blank=True, default="")
    cols = models.CharField(max_length=64, blank=True, default="")
    extra_json = models.JSONField(blank=True, null=True)

    class Meta:
        db_table = "xl_print_title"