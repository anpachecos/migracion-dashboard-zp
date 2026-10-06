"""
Persistencia: modelo intermedio <-> SQLite.

Es la unica capa que toca la base. Recibe el dict que produce `extract` y
escribe en las tablas `xl_*`, deduplicando por hash con `get_or_create` para
que capturar dos veces el mismo Excel no duplique los 359 estilos.

Dos decisiones que importan:

- Todo lo colgado de una version entra en una transaccion. Si algo falla a la
  mitad, no queda una version a medio escribir que luego se exporte incompleta.
- Los hashes son deterministas, asi que volver a capturar el mismo archivo
  produce exactamente las mismas claves de estilo. Eso es lo que hace que el
  test de comparacion celda por celda pueda comparar por hash.
"""

from django.db import transaction

from . import models
from .hashing import hash_de


class ResultadoPersistencia:
    """Contadores de lo guardado, para el log y el reporte final."""

    def __init__(self):
        self.version = None
        self.hojas = 0
        self.columnas = 0
        self.filas = 0
        self.tramos = 0
        self.etiquetas = 0
        self.estilos = 0
        self.dxfs = 0
        self.combinaciones = 0
        self.validaciones = 0
        self.condicionales = 0
        self.tablas = 0
        self.comentarios = 0
        self.imagenes = 0

    def __str__(self):
        return (
            f"{self.hojas} hojas, {self.estilos} estilos, {self.filas} filas, "
            f"{self.columnas} columnas, {self.tramos} tramos, "
            f"{self.etiquetas} etiquetas, {self.condicionales} reglas CF"
        )


# --------------------------------------------------------------------- #
# Estilos deduplicados
# --------------------------------------------------------------------- #

class CacheEstilos:
    """
    Traduce hashes del modelo a filas de la base, reutilizando lo ya guardado.

    Los hashes del modelo son los mismos que la columna `hash` de cada tabla,
    asi que la cache se puede indexar directamente por hash y no hace falta un
    mapa hash -> id en memoria.
    """

    def __init__(self):
        self._fuentes = {}
        self._rellenos = {}
        self._bordes = {}
        self._alineaciones = {}
        self._protecciones = {}
        self._formatos = {}
        self._estilos = {}
        self._dxfs = {}

    def fuente(self, hash_):
        if hash_ not in self._fuentes:
            fila, _ = models.Font.objects.get_or_create(hash=hash_)
            self._fuentes[hash_] = fila
        return self._fuentes[hash_]

    def relleno(self, hash_):
        if hash_ not in self._rellenos:
            fila, _ = models.Fill.objects.get_or_create(hash=hash_)
            self._rellenos[hash_] = fila
        return self._rellenos[hash_]

    def borde(self, hash_):
        if hash_ not in self._bordes:
            fila, _ = models.Border.objects.get_or_create(hash=hash_)
            self._bordes[hash_] = fila
        return self._bordes[hash_]

    def alineacion(self, hash_):
        if hash_ not in self._alineaciones:
            fila, _ = models.Alignment.objects.get_or_create(hash=hash_)
            self._alineaciones[hash_] = fila
        return self._alineaciones[hash_]

    def proteccion(self, hash_):
        if hash_ not in self._protecciones:
            fila, _ = models.Protection.objects.get_or_create(hash=hash_)
            self._protecciones[hash_] = fila
        return self._protecciones[hash_]

    def formato(self, hash_):
        if hash_ not in self._formatos:
            fila, _ = models.NumberFormat.objects.get_or_create(hash=hash_)
            self._formatos[hash_] = fila
        return self._formatos[hash_]

    def guardar_piezas(self, piezas):
        """Vuelca las seis tablas de componentes. Devuelve cuantos hay."""

        total = 0
        for hash_, datos in piezas.get("fonts", {}).items():
            models.Font.objects.get_or_create(hash=hash_, defaults={"data_json": datos})
            total += 1
        for hash_, datos in piezas.get("fills", {}).items():
            models.Fill.objects.get_or_create(hash=hash_, defaults={"data_json": datos})
            total += 1
        for hash_, datos in piezas.get("borders", {}).items():
            models.Border.objects.get_or_create(hash=hash_, defaults={"data_json": datos})
            total += 1
        for hash_, datos in piezas.get("alignments", {}).items():
            models.Alignment.objects.get_or_create(hash=hash_, defaults={"data_json": datos})
            total += 1
        for hash_, datos in pieces_protections(piezas).items():
            models.Protection.objects.get_or_create(hash=hash_, defaults={"data_json": datos})
            total += 1
        for hash_, datos in piezas.get("number_formats", {}).items():
            models.NumberFormat.objects.get_or_create(
                hash=hash_, defaults={"data_json": datos}
            )
            total += 1

        for hash_, datos in piezas.get("styles", {}).items():
            # Los seis FK son NOT NULL, asi que hay que resolver las piezas
            # antes de insertar la fila: no vale un `get_or_create(hash=...)`
            # porque fallaria al no trazer los componentes.
            piezas_estilo = {
                "font": self.fuente(datos["font"]),
                "fill": self.relleno(datos["fill"]),
                "border": self.borde(datos["border"]),
                "alignment": self.alineacion(datos["alignment"]),
                "protection": self.proteccion(datos["protection"]),
                "number_format": self.formato(datos["number_format"]),
            }
            fila, _ = models.Style.objects.get_or_create(hash=hash_, defaults=piezas_estilo)
            # En una fila ya existente (mismo hash en otra captura) los defaults
            # no se aplican, asi que se reasignan siempre.
            for campo, valor in piezas_estilo.items():
                setattr(fila, campo, valor)
            fila.save(update_fields=list(piezas_estilo))
            self._estilos[hash_] = fila
            total += 1

        return total

    def estilo(self, hash_):
        """Fila de `xl_style` para un hash, creandola si hace falta."""

        if hash_ is None:
            return None
        if hash_ not in self._estilos:
            fila = models.Style.objects.filter(hash=hash_).first()
            if fila is None:
                return None
            self._estilos[hash_] = fila
        return self._estilos[hash_]

    def guardar_dxfs(self, dxfs):
        """
        Guarda los estilos diferenciales y devuelve `hash -> fila`.

        Un dxf no tiene indice propio en la base: se guarda por hash y las
        reglas de formato condicional lo referencian por hash.
        """

        for datos in dxfs or []:
            hash_ = hash_de(datos)
            fila, _ = models.Dxf.objects.get_or_create(
                hash=hash_, defaults={"data_json": datos}
            )
            self._dxfs[hash_] = fila
        return self._dxfs

    def dxf(self, hash_):
        if hash_ is None:
            return None
        if hash_ not in self._dxfs:
            fila = models.Dxf.objects.filter(hash=hash_).first()
            if fila is None:
                return None
            self._dxfs[hash_] = fila
        return self._dxfs[hash_]


def pieces_protections(piezas):
    """Acceso a las protecciones con el mismo nombre que el resto."""

    return piezas.get("protections", {})


# --------------------------------------------------------------------- #
# Version completa
# --------------------------------------------------------------------- #

@transaction.atomic
def guardar_version(plantilla, modelo, notas_extra=""):
    """
    Guarda el modelo intermedio como una version nueva de `plantilla`.

    `plantilla` es una fila de `Template` ya creada. La version se crea
    inmutable y no se toca `current_version`: quien decide que queda vigente
    es `services.py`, para que capturar y publicar sean pasos distintos.
    """

    resultado = ResultadoPersistencia()
    estilos = CacheEstilos()

    resultado.estilos = estilos.guardar_piezas(modelo.get("estilos", {}))
    estilos.guardar_dxfs(modelo.get("dxfs", []))
    resultado.dxfs = len(estilos._dxfs)

    # Siguiente numero de version de esta plantilla.
    ultimo = (
        models.TemplateVersion.objects.filter(template=plantilla)
        .order_by("-version_no")
        .first()
    )
    numero = (ultimo.version_no + 1) if ultimo else 1

    version = models.TemplateVersion.objects.create(
        template=plantilla,
        version_no=numero,
        source_filename=modelo.get("source_filename") or "plantilla.xlsx",
        source_ext=modelo.get("source_ext") or ".xlsx",
        source_sha256=modelo.get("source_sha256") or "",
        status=models.TemplateVersion.Status.BORRADOR,
        notes=notas_extra or modelo.get("notas", ""),
        created_by=modelo.get("creado_por", ""),
    )
    resultado.version = version

    _guardar_workbook_meta(version, modelo)

    for hoja_modelo in modelo.get("hojas", []):
        _guardar_hoja(hoja_modelo, version, estilos, resultado)

    resultado.hojas = version.sheets.count()
    return resultado


def _guardar_workbook_meta(version, modelo):
    """`xl_workbook_meta`: theme crudo, defined names, props, calc props."""

    libro = modelo.get("workbook", {})

    models.WorkbookMeta.objects.create(
        version=version,
        theme_xml=libro.get("theme_xml") or "",
        defined_names_json=libro.get("defined_names"),
        workbook_props_json=libro.get("props"),
        calc_props_json=libro.get("calc_props"),
        extra_json=libro.get("extra"),
    )


def _guardar_hoja(hoja, version, estilos, resultado):
    """Una hoja y todo lo que cuelga de ella."""

    fila_hoja = models.Sheet.objects.create(
        version=version,
        position=hoja["position"],
        name=hoja["name"],
        state=hoja.get("state") or models.Sheet.State.VISIBLE,
        tab_color_json=hoja.get("tab_color_json"),
        default_row_height=hoja.get("default_row_height"),
        default_col_width=hoja.get("default_col_width"),
        sheet_view_json=hoja.get("sheet_view_json"),
        page_setup_json=hoja.get("page_setup_json"),
        margins_json=hoja.get("margins_json"),
        print_json=hoja.get("print_json"),
        header_footer_json=hoja.get("header_footer_json"),
        extra_json=hoja.get("extra_json"),
    )

    _guardar_columnas(fila_hoja, hoja.get("columns", []), estilos, resultado)
    _guardar_filas(fila_hoja, hoja.get("rows", []), estilos, resultado)
    _guardar_tramos(fila_hoja, hoja.get("style_runs", []), estilos, resultado)
    _guardar_etiquetas(fila_hoja, hoja.get("labels", []), resultado)
    _guardar_combinaciones(fila_hoja, hoja.get("merged", []), resultado)
    _guardar_validaciones(fila_hoja, hoja.get("data_validations", []), resultado)
    _guardar_condicionales(
        fila_hoja, hoja.get("conditional_formats", []), estilos, resultado
    )
    _guardar_autofiltro(fila_hoja, hoja.get("autofilter"), resultado)
    _guardar_tablas(fila_hoja, hoja.get("tables", []), resultado)
    _guardar_comentarios(fila_hoja, hoja.get("comments", []), resultado)
    _guardar_imagenes(fila_hoja, hoja.get("images", []), resultado)
    _guardar_titulos_impresion(fila_hoja, hoja.get("print_title"))


def _guardar_columnas(fila_hoja, columnas, estilos, resultado):
    for columna in columnas:
        models.Column.objects.create(
            sheet=fila_hoja,
            min_idx=columna["min_idx"],
            max_idx=columna["max_idx"],
            width=columna.get("width"),
            hidden=columna.get("hidden", False),
            best_fit=columna.get("best_fit", False),
            outline_level=columna.get("outline_level", 0),
            style=estilos.estilo(columna.get("style")),
        )
    resultado.columnas += len(columnas)


def _guardar_filas(fila_hoja, filas, estilos, resultado):
    models.Row.objects.bulk_create(
        [
            models.Row(
                sheet=fila_hoja,
                row_idx=fila["row_idx"],
                height=fila.get("height"),
                hidden=fila.get("hidden", False),
                outline_level=fila.get("outline_level", 0),
                style=estilos.estilo(fila.get("style")),
            )
            for fila in filas
        ],
        batch_size=1000,
    )
    resultado.filas += len(filas)


def _guardar_tramos(fila_hoja, tramos, estilos, resultado):
    """
    Tramos de estilo. Van en lote porque un archivo grande genera decenas de
    miles y crearlos uno a uno seria la parte lenta de la captura.
    """

    objetos = []
    cache_ids = estilos._estilos

    for tramo in tramos:
        hash_estilo = tramo.get("style")
        fila_estilo = cache_ids.get(hash_estilo) or estilos.estilo(hash_estilo)
        if fila_estilo is None:
            # Un tramo sin estilo resuelto no se puede guardar; se descarta
            # aqui y el reporte de la extraccion ya habra avisado.
            continue

        objetos.append(
            models.CellStyleRun(
                sheet=fila_hoja,
                row_idx=tramo["row_idx"],
                col_start=tramo["col_start"],
                col_end=tramo["col_end"],
                style=fila_estilo,
                role=tramo.get("role") or models.CellStyleRun.Role.DATA,
            )
        )

    models.CellStyleRun.objects.bulk_create(objetos, batch_size=2000)
    resultado.tramos += len(objetos)


def _guardar_etiquetas(fila_hoja, etiquetas, resultado):
    """
    Unico lugar donde queda texto del Excel original.

    Aca ya solo llegan celdas que `roles` marco como cabecera o leyenda, asi
    que no hay que filtrar de nuevo.
    """

    models.CellLabel.objects.bulk_create(
        [
            models.CellLabel(
                sheet=fila_hoja,
                row_idx=etiqueta["row_idx"],
                col_idx=etiqueta["col_idx"],
                value=etiqueta.get("value", ""),
                value_type=etiqueta.get("value_type", "s"),
            )
            for etiqueta in etiquetas
        ],
        batch_size=1000,
    )
    resultado.etiquetas += len(etiquetas)


def _guardar_combinaciones(fila_hoja, combinaciones, resultado):
    models.MergedRange.objects.bulk_create(
        [
            models.MergedRange(sheet=fila_hoja, ref=combinacion["ref"])
            for combinacion in combinaciones
        ],
        batch_size=500,
    )
    resultado.combinaciones += len(combinaciones)


def _guardar_validaciones(fila_hoja, validaciones, resultado):
    models.DataValidation.objects.bulk_create(
        [
            models.DataValidation(
                sheet=fila_hoja,
                sqref_json=validacion["sqref_json"],
                type=validacion.get("type", ""),
                formula1_json=validacion.get("formula1_json"),
                formula2_json=validacion.get("formula2_json"),
                options_json=validacion.get("options_json"),
            )
            for validacion in validaciones
        ],
        batch_size=500,
    )
    resultado.validaciones += len(validaciones)


def _guardar_condicionales(fila_hoja, condicionales, estilos, resultado):
    modelos = []
    cache_dxf = estilos._dxfs

    for regla in condicionales:
        hash_dxf = regla.get("dxf")
        fila_dxf = cache_dxf.get(hash_dxf) if hash_dxf else None
        if hash_dxf and fila_dxf is None:
            fila_dxf = estilos.dxf(hash_dxf)

        modelos.append(
            models.ConditionalFormat(
                sheet=fila_hoja,
                sqref_json=regla["sqref_json"],
                type=regla.get("type", ""),
                operator=regla.get("operator", ""),
                priority=regla.get("priority", 1),
                stop_if_true=regla.get("stop_if_true", False),
                text=regla.get("text", ""),
                time_period=regla.get("time_period", ""),
                rank=regla.get("rank"),
                percent=regla.get("percent"),
                bottom=regla.get("bottom"),
                std_dev=regla.get("std_dev"),
                above_average=regla.get("above_average"),
                equal_average=regla.get("equal_average"),
                formulas_json=regla.get("formulas_json"),
                color_scale_json=regla.get("color_scale_json"),
                data_bar_json=regla.get("data_bar_json"),
                icon_set_json=regla.get("icon_set_json"),
                dxf=fila_dxf,
            )
        )

    models.ConditionalFormat.objects.bulk_create(modelos, batch_size=500)
    resultado.condicionales += len(modelos)


def _guardar_autofiltro(fila_hoja, autofiltro, resultado):
    if not autofiltro:
        return

    models.Autofilter.objects.create(
        sheet=fila_hoja,
        ref=autofiltro.get("ref") or "",
        columns_json=autofiltro.get("columns_json"),
        sort_state_json=autofiltro.get("sort_state_json"),
        hidden_rows_json=autofiltro.get("hidden_rows_json"),
    )


def _guardar_tablas(fila_hoja, tablas, resultado):
    for tabla in tablas:
        models.Table.objects.create(
            sheet=fila_hoja,
            name=tabla.get("name") or "",
            display_name=tabla.get("display_name") or "",
            ref=tabla.get("ref") or "",
            table_json=tabla.get("table_json"),
        )
    resultado.tablas += len(tablas)


def _guardar_comentarios(fila_hoja, comentarios, resultado):
    for comentario in comentarios:
        models.CommentShell.objects.create(
            sheet=fila_hoja,
            cell_ref=comentario.get("cell_ref") or "",
            author=comentario.get("author") or "",
            text_json=comentario.get("text") or "",
        )
    resultado.comentarios += len(comentarios)


def _guardar_imagenes(fila_hoja, imagenes, resultado):
    for imagen in imagenes:
        models.ImageRef.objects.create(
            sheet=fila_hoja,
            anchor_json=imagen,
        )
    resultado.imagenes += len(imagenes)


def _guardar_titulos_impresion(fila_hoja, titulos):
    if not titulos:
        return

    models.PrintTitle.objects.create(
        sheet=fila_hoja,
        rows=titulos.get("rows", ""),
        cols=titulos.get("cols", ""),
    )


# --------------------------------------------------------------------- #
# Carga para el render
# --------------------------------------------------------------------- #

def cargar_version(version):
    """
    Lee una version de la base y devuelve el modelo intermedio.

    Es el espejo exacto de `guardar_version`: si algo se guarda, aqui se
    recupera con la misma forma. El render solo trabaja con esto.
    """

    estilos = CacheEstilos()

    modelo = {
        "version": version,
        "template_name": version.template.name,
        "export_filename": version.template.export_filename,
        "workbook": _cargar_workbook_meta(version),
        "estilos": {
            "fonts": _cargar_componente(models.Font),
            "fills": _cargar_componente(models.Fill),
            "borders": _cargar_componente(models.Border),
            "alignments": _cargar_componente(models.Alignment),
            "protections": _cargar_componente(models.Protection),
            "number_formats": _cargar_componente(models.NumberFormat),
            "styles": {},
        },
        "dxfs": [],
        "hojas": [],
    }

    # Los estilos referenciados por las hojas de esta version, no todos los de
    # la base: en una base con varias plantillas, cargar todo seria innecesario.
    hashes = _hashes_en_uso(version)

    for fila in models.Style.objects.filter(hash__in=hashes).select_related(
        "font", "fill", "border", "alignment", "protection", "number_format"
    ):
        # Las claves son hashes, no ids: el render resuelve piezas por hash y
        # asi el modelo de la base es identico al que devuelve `extract`.
        modelo["estilos"]["styles"][fila.hash] = {
            "font": fila.font.hash,
            "fill": fila.fill.hash,
            "border": fila.border.hash,
            "alignment": fila.alignment.hash,
            "protection": fila.protection.hash,
            "number_format": fila.number_format.hash,
        }
        estilos._estilos[fila.hash] = fila

    # El related_name por defecto de `ConditionalFormat.dxf` es el nombre de la
    # clase en minusculas, no el nombre del campo.
    hashes_dxf = set(
        models.ConditionalFormat.objects.filter(sheet__version=version)
        .exclude(dxf=None)
        .values_list("dxf_id", flat=True)
    )
    for fila in models.Dxf.objects.filter(id__in=hashes_dxf):
        modelo["dxfs"].append(fila.data_json)

    for fila_hoja in version.sheets.all().prefetch_related(
        "columns__style",
        "rows__style",
        "style_runs__style",
        "labels",
        "merged",
        "data_validations",
        "conditional_formats__dxf",
        "tables",
        "comments",
        "images",
    ):
        modelo["hojas"].append(_cargar_hoja(fila_hoja, estilos))

    return modelo


def _hashes_en_uso(version):
    """
    Hashes de estilo referenciados por las hojas de esta version.

    Se recorren los `style_id` pero se devuelven los `hash` de esas filas, que
    es por donde el render busca. Devolver ids aqui haria que el filtro por
    hash no encontrase nada.
    """

    ids = set()

    ids.update(
        models.Column.objects.filter(sheet__version=version)
        .exclude(style=None)
        .values_list("style_id", flat=True)
    )
    ids.update(
        models.Row.objects.filter(sheet__version=version)
        .exclude(style=None)
        .values_list("style_id", flat=True)
    )
    ids.update(
        models.CellStyleRun.objects.filter(sheet__version=version)
        .exclude(style=None)
        .values_list("style_id", flat=True)
    )

    if not ids:
        return set()

    return set(
        models.Style.objects.filter(id__in=ids).values_list("hash", flat=True)
    )


def _cargar_componente(modelo):
    """Todos los registros de una tabla de componentes, por hash."""

    return {fila.hash: fila.data_json for fila in modelo.objects.all()}


def _cargar_workbook_meta(version):
    meta = getattr(version, "meta", None)
    if meta is None:
        return {}

    return {
        "theme_xml": meta.theme_xml,
        "defined_names": meta.defined_names_json,
        "props": meta.workbook_props_json,
        "calc_props": meta.calc_props_json,
    }


def _hash_de_estilo(objeto):
    """
    Hash de estilo de una relacion, o None.

    `_hash_en_uso` guarda hashes, asi que al releer hay que volver a convertir
    el id de la base al hash que espera el render.
    """

    if objeto is None:
        return None
    if objeto.style_id is None:
        return None
    return objeto.style.hash


def _cargar_hoja(fila_hoja, estilos):
    """Vuelve una hoja a la forma que el render espera."""

    return {
        "position": fila_hoja.position,
        "name": fila_hoja.name,
        "state": fila_hoja.state,
        "tab_color_json": fila_hoja.tab_color_json,
        "default_row_height": fila_hoja.default_row_height,
        "default_col_width": fila_hoja.default_col_width,
        "sheet_view_json": fila_hoja.sheet_view_json,
        "page_setup_json": fila_hoja.page_setup_json,
        "margins_json": fila_hoja.margins_json,
        "print_json": fila_hoja.print_json,
        "header_footer_json": fila_hoja.header_footer_json,
        "extra_json": fila_hoja.extra_json,
        "columns": [
            {
                "min_idx": columna.min_idx,
                "max_idx": columna.max_idx,
                "width": columna.width,
                "hidden": columna.hidden,
                "best_fit": columna.best_fit,
                "outline_level": columna.outline_level,
                "style": _hash_de_estilo(columna),
            }
            for columna in fila_hoja.columns.all()
        ],
        "rows": [
            {
                "row_idx": fila.row_idx,
                "height": fila.height,
                "hidden": fila.hidden,
                "outline_level": fila.outline_level,
                "style": _hash_de_estilo(fila),
            }
            for fila in fila_hoja.rows.all()
        ],
        "style_runs": [
            {
                "row_idx": tramo.row_idx,
                "col_start": tramo.col_start,
                "col_end": tramo.col_end,
                "style": tramo.style.hash,
                "role": tramo.role,
            }
            for tramo in fila_hoja.style_runs.all()
        ],
        "labels": [
            {
                "row_idx": etiqueta.row_idx,
                "col_idx": etiqueta.col_idx,
                "value": etiqueta.value,
                "value_type": etiqueta.value_type,
            }
            for etiqueta in fila_hoja.labels.all()
        ],
        "merged": [{"ref": combinacion.ref} for combinacion in fila_hoja.merged.all()],
        "data_validations": [
            {
                "sqref_json": validacion.sqref_json,
                "type": validacion.type,
                "formula1_json": validacion.formula1_json,
                "formula2_json": validacion.formula2_json,
                "options_json": validacion.options_json,
            }
            for validacion in fila_hoja.data_validations.all()
        ],
        "conditional_formats": [
            {
                "sqref_json": regla.sqref_json,
                "type": regla.type,
                "operator": regla.operator,
                "priority": regla.priority,
                "stop_if_true": regla.stop_if_true,
                "text": regla.text,
                "time_period": regla.time_period,
                "rank": regla.rank,
                "percent": regla.percent,
                "bottom": regla.bottom,
                "std_dev": regla.std_dev,
                "above_average": regla.above_average,
                "equal_average": regla.equal_average,
                "formulas_json": regla.formulas_json,
                "color_scale_json": regla.color_scale_json,
                "data_bar_json": regla.data_bar_json,
                "icon_set_json": regla.icon_set_json,
                "dxf": regla.dxf.hash if regla.dxf_id else None,
            }
            for regla in fila_hoja.conditional_formats.all()
        ],
        "autofilter": _cargar_autofiltro(fila_hoja),
        "tables": [
            {
                "name": tabla.name,
                "display_name": tabla.display_name,
                "ref": tabla.ref,
                "table_json": tabla.table_json,
            }
            for tabla in fila_hoja.tables.all()
        ],
        "comments": [
            {
                "cell_ref": comentario.cell_ref,
                "author": comentario.author,
                "text": comentario.text_json,
            }
            for comentario in fila_hoja.comments.all()
        ],
        "images": [imagen.anchor_json for imagen in fila_hoja.images.all()],
        "print_title": _cargar_print_title(fila_hoja),
    }


def _cargar_autofiltro(fila_hoja):
    autofiltro = getattr(fila_hoja, "autofilter", None)
    if autofiltro is None:
        return None

    return {
        "ref": autofiltro.ref,
        "columns_json": autofiltro.columns_json,
        "sort_state_json": autofiltro.sort_state_json,
        "hidden_rows_json": autofiltro.hidden_rows_json,
    }


def _cargar_print_title(fila_hoja):
    titulo = getattr(fila_hoja, "print_title", None)
    if titulo is None:
        return None
    return {"rows": titulo.rows, "cols": titulo.cols}