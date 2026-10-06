"""
Parametros de exportacion de una plantilla.

`ExportOptions` decide que se conserva del Excel original al generar la
plantilla vacia. Los valores por defecto estan pensados para que la plantilla
sirva para capturar datos nuevos: se quedan las cabeceras y la leyenda (sin
ellas no hay nada que rellenar), y se vacia todo lo demas.
"""

from dataclasses import dataclass, field, asdict


class OpcionNoSoportada(ValueError):
    """
    Se pidio una opcion que el motor todavia no sabe aplicar.

    Existe para que una opcion no implementada se note. Aceptarla y exportar
    igual es peor que rechazarla: el archivo sale bien pero sin la formula que
    se pidio, y el error se descubre cuando alguien abre el Excel.
    """


class DataRowsMode:
    """Como se replican las filas de datosOriginales."""

    EXACT = "exact"
    PROTOTYPE = "prototype"


@dataclass(frozen=True)
class ExportOptions:
    """
    Opciones de exportacion.

    Atributos:
        keep_labels: conserva el texto de celdas con rol `HEADER` y `LEGEND`.
        keep_formulas: conserva las formulas. Por defecto False: una plantilla
            de captura no debe arrastrar calculos sobre datos que ya no estan.
        keep_comment_text: conserva el texto de los comentarios. Por defecto
            False porque el texto es contenido, no formato.
        keep_data_validation_lists: conserva listas desplegables y rangos.
        keep_hidden_rows: conserva el ocultamiento de filas que trae el archivo.
        data_rows_mode: `exact` replica los estilos de todas las filas
            originales; `prototype` repite N veces la fila tipo.
        prototype_repeat: cuantas filas copia `prototype`.
        keep_sheet_state: conserva hojas ocultas. Si es False, la plantilla
            exporta todas las hojas visibles (un archivo de captura no deberia
            esconder datos).
        unknown_role_as: que se hace con las celdas de rol `UNKNOWN`, que
            aparecen cuando la heuristica no es confiable. Tratar como `data`
            (valor por defecto) es la opcion segura: no filtra informacion.
    """

    keep_labels: bool = True
    keep_formulas: bool = False
    keep_comment_text: bool = False
    keep_data_validation_lists: bool = True
    keep_hidden_rows: bool = True
    keep_sheet_state: bool = True
    data_rows_mode: str = DataRowsMode.EXACT
    prototype_repeat: int = 50
    unknown_role_as: str = "data"

    def normalized(self):
        """
        Devuelve una copia con valores validos para datos guardados.

        Un valor fuera de dominio se corrige al equivalente mas cercano
        (`data_rows_mode` desconocido vuelve a `exact`, `unknown_role_as` a
        `data`), porque son valores que nunca debieron existir y corregir los
        deja funcionando.

        Lo que no se corrige es lo que el motor no sabe hacer: pedir
        `keep_formulas` o `data_rows_mode=prototype` es una peticion explicita
        que hoy no se puede cumplir, y se rechaza con `OpcionNoSoportada` en
        vez de exportar un archivo que no cumple lo pedido.
        """

        campos = asdict(self)

        if campos["data_rows_mode"] not in (
            DataRowsMode.EXACT,
            DataRowsMode.PROTOTYPE,
        ):
            campos["data_rows_mode"] = DataRowsMode.EXACT

        if campos["unknown_role_as"] not in ("data", "header", "legend"):
            campos["unknown_role_as"] = "data"

        if campos["prototype_repeat"] < 1:
            campos["prototype_repeat"] = 1

        self._rechazar_lo_no_soportado(campos)

        return ExportOptions(**campos)

    def _rechazar_lo_no_soportado(self, campos):
        """Falla si se pide algo que el render todavia no aplica."""

        if campos["keep_formulas"]:
            raise OpcionNoSoportada(
                "keep_formulas todavia no esta implementado: el render escribe "
                "los valores de las celdas, no las formulas. Exporta con "
                "keep_formulas=0 mientras tanto."
            )

        if campos["data_rows_mode"] == DataRowsMode.PROTOTYPE:
            raise OpcionNoSoportada(
                "data_rows_mode=prototype todavia no esta implementado: solo "
                "esta disponible 'exact'."
            )

        if campos["unknown_role_as"] != "data":
            raise OpcionNoSoportada(
                f"unknown_role_as='{campos['unknown_role_as']}' todavia no esta "
                "implementado: solo esta disponible 'data'."
            )