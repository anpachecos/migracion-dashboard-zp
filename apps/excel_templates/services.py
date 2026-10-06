"""
Servicios del motor de plantillas Excel.

Une `extract`, `persist` y `render` en las dos operaciones que el modulo
expone: capturar un Excel como plantilla y exportar una plantilla vacia.

La regla de versionado vive aqui y no en `persist`: capturar crea una version
en `BORRADOR` y no publica nada. Publicar y hacer rollback son decisiones
explicitas, que es lo que la Fase 2 necesita para no pisar una plantilla que
alguien esta editando.
"""

import logging

from django.db import transaction

from . import extract, hashing, models, persist, render
from .options import ExportOptions, OpcionNoSoportada

logger = logging.getLogger(__name__)


class ErrorDePlantilla(Exception):
    """Error de negocio del modulo, con mensaje para el usuario."""


class ErrorDePlantillaDuplicada(ErrorDePlantilla):
    """
    El archivo subido ya fue capturado antes.

    Va aparte de `ErrorDePlantilla` para que la vista pueda responder 409 en vez
    de 400: no es un dato invalido sino un conflicto, y el modal lo muestra
    distinto porque la accion que corresponde es elegir la plantilla que ya
    existe en vez de volver a subir.
    """


# --------------------------------------------------------------------- #
# Captura
# --------------------------------------------------------------------- #

def capturar(ruta, nombre=None, descripcion="", notas="", creado_por="",
             publicar=True, plantilla=None):
    """
    Captura un `.xlsx`/`.xlsm` como plantilla y devuelve el resultado.

    `plantilla` dice a que plantilla se le agrega la version. Sin ella se usa
    (o se crea) la que tenga el nombre `nombre`. Subir sobre una plantilla
    existente **no** cambia su nombre ni el nombre con el que se descarga: eso
    se decide al crearla, y cambiarlo cada vez que se sube un archivo con otro
    nombre dejaria enlaces compartidos apuntando a archivos distintos.

    Si `publicar` es True (por defecto) la version nueva queda vigente y las
    anteriores se archivan, pero **no se borra ninguna**: el historial queda
    intacto y el rollback es volver a publicar una anterior.
    """

    # El nombre se valida primero: es un chequeo de una comparacion y no de
    # abrir el archivo. Si se valida despues, un `nombre` vacio con una ruta
    # inexistente falla con `FileNotFoundError` en vez de con el mensaje que
    # explica el problema.
    if plantilla is None:
        if not nombre or not nombre.strip():
            raise ErrorDePlantilla("El nombre de la plantilla no puede quedar vacio.")
        nombre = nombre.strip()
    else:
        # El nombre lo tiene la plantilla destino; lo que llega en el query se
        # ignora a proposito para que subir a "Versión Zona Paga" no la
        # renombre a lo que traiga el formulario.
        nombre = plantilla.name

    # El SHA se calcula antes de extraer: el archivo son varios megas y la
    # extraccion completa cuesta bastante mas que leerlo. Asi el duplicado se
    # detecta sin haber tocado la base.
    _rechazar_si_ya_capturado(ruta)

    modelo = extract.extraer(
        ruta,
        nombre=nombre,
        descripcion=descripcion,
        notas=notas,
        creado_por=creado_por,
    )

    reporte = modelo.get("reporte") or {}
    if reporte.get("hay_degradaciones"):
        logger.warning(
            "captura de '%s' con degradaciones: %s",
            nombre,
            _resumen_degradaciones(reporte),
        )

    if plantilla is None:
        plantilla, creada = _obtener_plantilla(nombre, descripcion, ruta)
    else:
        creada = False

    resultado = persist.guardar_version(plantilla, modelo)

    if publicar:
        publicar_version(plantilla, resultado.version)

    plantilla.refresh_from_db()

    logger.info(
        "plantilla '%s' v%s capturada desde %s: %s",
        plantilla.name,
        resultado.version.version_no,
        resultado.version.source_filename,
        resultado,
    )

    return {
        "plantilla": plantilla,
        "version": resultado.version,
        "resultado": resultado,
        "reporte": modelo.get("reporte"),
        "creada": creada,
    }


def _rechazar_si_ya_capturado(ruta):
    """
    Falla si el archivo es byte a byte igual a una version ya capturada.

    El chequeo es global, no por plantilla: un SHA igual es el mismo archivo,
    y volver a subirlo casi siempre es un clic de mas y no una plantilla
    nueva. El mensaje dice donde esta para que la accion sea "actualizar esa",
    no "buscar el archivo correcto".
    """

    sha = hashing.sha256_archivo(ruta)

    repetida = (
        models.TemplateVersion.objects.filter(source_sha256=sha)
        .select_related("template")
        .first()
    )

    if repetida is None:
        return

    # Subir el mismo archivo sobre la misma plantilla tampoco crea nada util:
    # el formato resultante seria identico al que ya esta vigente.
    raise ErrorDePlantillaDuplicada(
        f"Ese archivo ya fue capturado como la plantilla "
        f"'{repetida.template.name}', version {repetida.version_no}. "
        f"No se creo una version nueva. Si lo que quieres es actualizarla, "
        f"sube el archivo modificado."
    )


def _obtener_plantilla(nombre, descripcion, ruta):
    """
    Devuelve la plantilla con ese nombre, creandola si no existe.

    El nombre de archivo exportado se deriva del nombre del archivo fuente,
    conservando su nombre pero con la extension en minuscula (el ejemplo llega
    como `.XLSX` en mayuscula y asi lo descarga el navegador).
    """

    plantilla = models.Template.objects.filter(name=nombre).first()

    if plantilla is not None:
        return plantilla, False

    archivo = ruta.replace("\\", "/").split("/")[-1]
    export_filename = _normalizar_nombre_export(archivo)

    plantilla = models.Template.objects.create(
        name=nombre,
        export_filename=export_filename,
        description=descripcion,
    )
    return plantilla, True


def _normalizar_nombre_export(archivo):
    """
    `ZONA_PAGA_V764_MARTES.XLSX` -> `ZONA_PAGA_V764_MARTES.xlsx`.
    Los `.xlsm` también se descargan como `.xlsx`, porque el render no conserva
    el proyecto VBA y siempre produce un libro sin macros.

    La extension en minuscula es lo que usan los navegadores y lo que espera
    el usuario; el resto del nombre se respeta tal cual porque puede venir con
    espacios o acentos que forman parte del nombre real.
    """

    base, _, extension = archivo.rpartition(".")
    if not base:
        return archivo

    extension = extension.lower()
    if extension == "xlsm":
        extension = "xlsx"

    return f"{base}.{extension}"


@transaction.atomic
def publicar_version(plantilla, version):
    """
    Marca una version como vigente y archiva las anteriores.

    No borra nada: `current_version_id` es el unico puntero que define cual es
    la plantilla vigente, asi que el rollback es volver a publicar otra.
    """

    models.TemplateVersion.objects.filter(
        template=plantilla, status=models.TemplateVersion.Status.VIGENTE
    ).exclude(pk=version.pk).update(status=models.TemplateVersion.Status.ARCHIVADA)

    version.status = models.TemplateVersion.Status.VIGENTE
    version.save(update_fields=["status"])

    plantilla.current_version = version
    plantilla.save(update_fields=["current_version", "updated_at"])

    return plantilla


def hacer_rollback(plantilla, version):
    """Deja vigente una version anterior. El historial no se toca."""

    if version.template_id != plantilla.id:
        raise ErrorDePlantilla(
            "La version indicada pertenece a otra plantilla."
        )

    return publicar_version(plantilla, version)


# --------------------------------------------------------------------- #
# Exportacion
# --------------------------------------------------------------------- #

def listar_plantillas(solo_vigentes=True):
    """Plantillas con su version vigente, para el selector de la web."""

    consulta = models.Template.objects.all()

    if solo_vigentes:
        consulta = consulta.filter(current_version__isnull=False)

    return consulta.select_related("current_version").order_by("name")


def editar_metadatos(plantilla, nombre, export_filename, descripcion=""):
    """Actualiza los metadatos administrativos, sin tocar ninguna version."""

    nombre = (nombre or "").strip()
    export_filename = (export_filename or "").strip()
    descripcion = (descripcion or "").strip()

    if not nombre:
        raise ErrorDePlantilla("El nombre de la plantilla no puede quedar vacio.")

    if not export_filename:
        raise ErrorDePlantilla("El nombre del archivo de descarga no puede quedar vacio.")

    if any(separador in export_filename for separador in ("/", "\\")):
        raise ErrorDePlantilla(
            "El nombre del archivo de descarga no puede contener rutas."
        )

    base, punto, extension = export_filename.rpartition(".")
    if not punto or not base:
        export_filename = f"{export_filename}.xlsx"
    elif extension.lower() not in ("xlsx", "xlsm"):
        raise ErrorDePlantilla("El archivo de descarga debe terminar en .xlsx o .xlsm.")
    elif extension.lower() == "xlsm":
        export_filename = f"{base}.xlsx"
    else:
        export_filename = f"{base}.xlsx"

    repetida = models.Template.objects.filter(name=nombre).exclude(pk=plantilla.pk).exists()
    if repetida:
        raise ErrorDePlantilla(f"Ya existe otra plantilla llamada '{nombre}'.")

    plantilla.name = nombre
    plantilla.export_filename = export_filename
    plantilla.description = descripcion
    plantilla.save(update_fields=["name", "export_filename", "description", "updated_at"])
    return plantilla


VERDADEROS = ("1", "true", "yes", "si", "t")
FALSOS = ("0", "false", "no", "f")


def opciones_desde_query(params):
    """
    Traduce los parametros de la URL a `ExportOptions`.

    Los valores se validan en vez de aceptarse: un `data_rows_mode`
    desconocido que se cuela por la query no debe cambiar el comportamiento de
    la exportacion sin que nadie lo note.
    """

    base = ExportOptions()

    def _bool(nombre):
        if nombre not in params:
            return None
        valor = str(params.get(nombre)).strip().lower()
        if valor in VERDADEROS:
            return True
        if valor in FALSOS:
            return False
        raise ErrorDePlantilla(
            f"El parametro '{nombre}' debe ser verdadero o falso, no '{valor}'."
        )

    def _bool_defecto(nombre, defecto):
        valor = _bool(nombre)
        return defecto if valor is None else valor

    modo = str(params.get("data_rows_mode") or "").strip().lower()
    if modo and modo not in ("exact", "prototype"):
        raise ErrorDePlantilla(
            f"data_rows_mode '{modo}' no valido. Use 'exact' o 'prototype'."
        )

    repetir = 1
    if params.get("prototype_repeat"):
        try:
            repetir = max(1, int(params["prototype_repeat"]))
        except (TypeError, ValueError):
            raise ErrorDePlantilla("prototype_repeat debe ser un numero entero.")

    # Se lee del query aunque hoy no se pueda aplicar: si el parametro no se
    # lee, `?unknown_role_as=header` se pierde en silencio y nadie se entera de
    # que el motor no honro la peticion.
    rol = str(params.get("unknown_role_as") or "").strip().lower()
    if rol and rol not in ("data", "header", "legend"):
        raise ErrorDePlantilla(
            f"unknown_role_as '{rol}' no valido. Use 'data', 'header' o 'legend'."
        )

    return _normalizar(
        ExportOptions(
            keep_labels=_bool_defecto("keep_labels", base.keep_labels),
            keep_formulas=_bool_defecto("keep_formulas", base.keep_formulas),
            keep_comment_text=_bool_defecto(
                "keep_comment_text", base.keep_comment_text
            ),
            keep_data_validation_lists=_bool_defecto(
                "keep_data_validation_lists", base.keep_data_validation_lists
            ),
            keep_hidden_rows=_bool_defecto("keep_hidden_rows", base.keep_hidden_rows),
            keep_sheet_state=_bool_defecto("keep_sheet_state", base.keep_sheet_state),
            data_rows_mode=modo or base.data_rows_mode,
            prototype_repeat=repetir,
            unknown_role_as=rol or base.unknown_role_as,
        )
    )


def _normalizar(opciones):
    """
    Aplica `ExportOptions.normalized` traduciendo el error.

    `OpcionNoSoportada` es un `ValueError` de la capa de opciones; la vista
    solo conoce `ErrorDePlantilla`, asi que se traduce aca para que un
    `?keep_formulas=1` responda 400 con un mensaje util en vez de un 500.
    """

    try:
        return opciones.normalized()
    except OpcionNoSoportada as error:
        raise ErrorDePlantilla(str(error))


def exportar(plantilla, version=None, opciones=None):
    """
    Genera el `.xlsx` vacio de una plantilla y devuelve los bytes.

    `version` permite exportar una version que no es la vigente (util para
    comparar o para recuperar una anterior). Por defecto usa `current_version`.
    """

    version = version or plantilla.current_version

    if version is None:
        raise ErrorDePlantilla(
            f"La plantilla '{plantilla.name}' no tiene ninguna version capturada."
        )

    if version.template_id != plantilla.id:
        raise ErrorDePlantilla("La version indicada pertenece a otra plantilla.")

    modelo = persist.cargar_version(version)
    datos, reporte = render.renderizar(modelo, opciones or ExportOptions())

    if reporte.hay_degradaciones:
        logger.warning(
            "exportacion de '%s' v%s con degradaciones: %s",
            plantilla.name,
            version.version_no,
            reporte,
        )

    return {
        "datos": datos,
        "nombre": plantilla.export_filename,
        "version": version,
        "reporte": reporte,
    }


def corregir_roles(hoja, cambios):
    """
    Cambia el rol de celdas de una hoja sin reimportar el Excel.

    `cambios` es `{"3": "HEADER"}` con el indice de fila (1-based) y el rol
    nuevo, o `{"3": {"5": "DATA"}}` para celdas concretas. Es la via para
    que el usuario corrija la heuristica: si una fila de datos quedo marcada
    como cabecera, se cambia aqui y la proxima exportacion la respeta.
    """

    roles_validos = {r for r, _ in models.CellStyleRun.Role.choices}

    actualizados = 0

    for fila, valor in cambios.items():
        try:
            indice_fila = int(fila)
        except (TypeError, ValueError):
            raise ErrorDePlantilla(f"Indice de fila invalido: {fila!r}")

        if isinstance(valor, dict):
            for columna, rol in valor.items():
                if rol not in roles_validos:
                    raise ErrorDePlantilla(f"Rol invalido: {rol!r}")
                actualizados += _corregir_tramo(hoja, indice_fila, int(columna), rol)
            continue

        if valor not in roles_validos:
            raise ErrorDePlantilla(f"Rol invalido: {valor!r}")

        actualizados += hoja.style_runs.filter(row_idx=indice_fila).update(role=valor)

    return actualizados


def _corregir_tramo(hoja, fila, columna, rol):
    """Cambia el rol del tramo que cubre una celda concreta."""

    for tramo in hoja.style_runs.filter(row_idx=fila):
        if tramo.col_start <= columna <= tramo.col_end:
            tramo.role = rol
            tramo.save(update_fields=["role"])
            return 1
    return 0


# --------------------------------------------------------------------- #
# Reporte
# --------------------------------------------------------------------- #

def _resumen_degradaciones(reporte):
    """Conteo por nivel, para una linea de log."""

    conteo = {}
    for entrada in reporte.get("entradas", []):
        conteo[entrada["nivel"]] = conteo.get(entrada["nivel"], 0) + 1
    return conteo


def resumen_degradaciones(reporte):
    """Conteo por nivel de un reporte, para el log y el reporte final."""

    return _resumen_degradaciones(reporte or {})
