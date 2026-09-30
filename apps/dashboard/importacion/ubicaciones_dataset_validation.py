"""Validación semántica del dataset neutral de ubicaciones esperadas."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
import numbers
import re


CAMPO_FILA_ORIGEN = "_fila_origen"


@dataclass(frozen=True)
class IncidenciaUbicacion:
    indice_dataset: int
    fila_origen: object
    idds: str | None
    campo: str
    codigo: str
    mensaje: str
    valor: object = None


@dataclass(frozen=True)
class ResultadoValidacionUbicaciones:
    registros: tuple
    amids_presentes: frozenset
    incidencias: tuple

    @property
    def es_valido(self):
        return not self.incidencias

    @property
    def total_filas_con_error(self):
        return len({incidencia.indice_dataset for incidencia in self.incidencias})


def validar_dataset_ubicaciones(filas, referencia_laboratorio):
    """Valida completamente una colección materializada de mappings neutrales."""
    filas = list(filas)
    incidencias = []
    candidatos = []
    ocurrencias_idds = {}

    for indice, fila_original in enumerate(filas):
        fila = dict(fila_original)
        fila_origen = fila.pop(CAMPO_FILA_ORIGEN, None)

        amid, error_idds = _normalizar_idds(fila.get("IDDS"))
        if error_idds:
            incidencias.append(_incidencia(
                indice, fila_origen, None, "IDDS", error_idds[0],
                error_idds[1], fila.get("IDDS"),
            ))

        nombre = _texto_requerido(fila.get("NOMBRE"))
        if nombre is None:
            incidencias.append(_incidencia(
                indice, fila_origen, amid, "NOMBRE", "required",
                "El nombre es obligatorio y no puede estar vacío.",
                fila.get("NOMBRE"),
            ))

        operativa, error_operativa = _normalizar_operativa(fila.get("OPERATIVA"))
        if error_operativa:
            incidencias.append(_incidencia(
                indice, fila_origen, amid, "OPERATIVA", "invalid_choice",
                "Valor no permitido. Use SI, SÍ o NO.", fila.get("OPERATIVA"),
            ))

        latitud = longitud = radio = None
        if operativa is True:
            latitud = _validar_numero(
                fila, "LATITUD_ESPERADA", "latitud", -90, 90,
                indice, fila_origen, amid, incidencias,
            )
            longitud = _validar_numero(
                fila, "LONGITUD_ESPERADA", "longitud", -180, 180,
                indice, fila_origen, amid, incidencias,
            )
            radio = _validar_numero(
                fila, "RADIO_METROS", "radio", None, None,
                indice, fila_origen, amid, incidencias,
            )
            if radio is not None and radio <= 0:
                incidencias.append(_incidencia(
                    indice, fila_origen, amid, "RADIO_METROS", "not_positive",
                    "El radio debe ser un número mayor que 0.", fila.get("RADIO_METROS"),
                ))
            if latitud == 0 and longitud == 0:
                incidencias.append(_incidencia(
                    indice, fila_origen, amid, "LATITUD_ESPERADA", "zero_pair",
                    "La pareja de coordenadas (0, 0) no es válida para Operativa=SI.",
                    "0, 0",
                ))

        normalizada = dict(fila)
        normalizada.update({
            "AMID": amid,
            "IDDS": amid,
            "NOMBRE": nombre,
            "SERIE_VALIDADOR": _texto_opcional(fila.get("SERIE_VALIDADOR")),
        })

        if operativa is True:
            normalizada.update({
                "LATITUD_ESPERADA": latitud,
                "LONGITUD_ESPERADA": longitud,
                "RADIO_METROS": radio,
                "OPERATIVA": 1,
                "ORIGEN_UBICACION": "excel",
            })
        elif operativa is False:
            normalizada.update({
                "NOMBRE": referencia_laboratorio["NOMBRE"],
                "LATITUD_ESPERADA": referencia_laboratorio["LATITUD_ESPERADA"],
                "LONGITUD_ESPERADA": referencia_laboratorio["LONGITUD_ESPERADA"],
                "RADIO_METROS": referencia_laboratorio["RADIO_METROS"],
                "OPERATIVA": 0,
                "ORIGEN_UBICACION": "laboratorio",
            })

        candidatos.append(normalizada)
        if amid is not None:
            ocurrencias_idds.setdefault(amid, []).append(
                (indice, fila_origen, fila.get("IDDS"))
            )

    for amid, ocurrencias in ocurrencias_idds.items():
        if len(ocurrencias) < 2:
            continue
        if all(fila is not None for _, fila, _ in ocurrencias):
            referencias = _unir_referencias([
                str(fila) for _, fila, _ in ocurrencias
            ])
            mensaje = f"IDDS {amid} duplicado en filas {referencias}."
        else:
            referencias = _unir_referencias([
                _referencia_legible(indice, fila)
                for indice, fila, _ in ocurrencias
            ])
            mensaje = f"IDDS {amid} duplicado en {referencias}."
        for indice, fila_origen, valor in ocurrencias:
            incidencias.append(_incidencia(
                indice, fila_origen, amid, "IDDS", "duplicate", mensaje, valor,
            ))

    if incidencias:
        return ResultadoValidacionUbicaciones((), frozenset(), tuple(incidencias))

    registros = tuple(candidatos)
    amids_presentes = frozenset(registro["AMID"] for registro in registros)
    return ResultadoValidacionUbicaciones(registros, amids_presentes, ())


def formatear_reporte_validacion(resultado):
    resumen = resumir_incidencias(resultado)
    lineas = [
        "No se importó Version_DB.",
        "",
        f"Se encontraron {resumen}.",
        "Oracle no fue modificado.",
        "",
    ]
    for incidencia in resultado.incidencias:
        origen = _referencia_legible(
            incidencia.indice_dataset, incidencia.fila_origen
        ).capitalize()
        idds = incidencia.idds or "sin IDDS válido"
        lineas.append(f"{origen} | IDDS {idds} | {incidencia.campo}")
        lineas.append(
            f"Valor {_valor_seguro(incidencia.valor)}. {incidencia.mensaje}"
        )
        lineas.append("")
    return "\n".join(lineas).rstrip()


def resumir_incidencias(resultado):
    total_errores = len(resultado.incidencias)
    total_filas = resultado.total_filas_con_error
    palabra_error = "error" if total_errores == 1 else "errores"
    palabra_fila = "fila" if total_filas == 1 else "filas"
    return f"{total_errores} {palabra_error} en {total_filas} {palabra_fila}"


def _normalizar_idds(valor):
    if valor is None or isinstance(valor, bool):
        return None, (
            "required", "El IDDS es obligatorio y debe ser un entero positivo."
        )

    numero = None
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None, (
                "required", "El IDDS es obligatorio y no puede estar vacío."
            )
        if not re.fullmatch(r"[0-9]+", texto):
            return None, (
                "invalid_integer",
                "El IDDS debe contener solo dígitos, sin decimales ni notación científica.",
            )
        numero = int(texto)
    elif isinstance(valor, numbers.Integral):
        numero = int(valor)
    elif isinstance(valor, numbers.Real):
        numero_float = float(valor)
        if not math.isfinite(numero_float) or not numero_float.is_integer():
            return None, (
                "invalid_integer",
                "El IDDS debe ser un número entero finito, sin truncamiento.",
            )
        numero = int(numero_float)
    elif isinstance(valor, Decimal):
        try:
            if not valor.is_finite() or valor != valor.to_integral_value():
                raise InvalidOperation
            numero = int(valor)
        except (InvalidOperation, ValueError, OverflowError):
            return None, (
                "invalid_integer",
                "El IDDS debe ser un número entero finito, sin truncamiento.",
            )
    else:
        return None, ("invalid_integer", "El IDDS debe ser un entero válido.")

    if numero <= 0:
        return None, ("not_positive", "El IDDS debe ser mayor que 0.")
    return str(numero), None


def _normalizar_operativa(valor):
    if not isinstance(valor, str):
        return None, True
    texto = valor.strip().upper()
    if texto in {"SI", "SÍ"}:
        return True, False
    if texto == "NO":
        return False, False
    return None, True


def _validar_numero(
    fila, campo, etiqueta, minimo, maximo,
    indice, fila_origen, amid, incidencias,
):
    valor = fila.get(campo)
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        incidencias.append(_incidencia(
            indice, fila_origen, amid, campo, "required",
            f"La {etiqueta} es obligatoria cuando Operativa=SI.", valor,
        ))
        return None
    numero = _numero_finito(valor)
    if numero is None:
        incidencias.append(_incidencia(
            indice, fila_origen, amid, campo, "invalid_number",
            f"La {etiqueta} debe ser un número finito.", valor,
        ))
        return None
    if minimo is not None and not minimo <= numero <= maximo:
        incidencias.append(_incidencia(
            indice, fila_origen, amid, campo, "out_of_range",
            f"La {etiqueta} debe estar en el rango [{minimo}, {maximo}].", valor,
        ))
        return None
    return numero


def _numero_finito(valor):
    if isinstance(valor, bool):
        return None
    try:
        if isinstance(valor, str):
            valor = valor.strip().replace(",", ".")
        numero = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return numero if math.isfinite(numero) else None


def _texto_requerido(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto if texto and texto.lower() != "nan" else None


def _texto_opcional(valor):
    return _texto_requerido(valor)


def _incidencia(indice, fila_origen, idds, campo, codigo, mensaje, valor):
    return IncidenciaUbicacion(
        indice_dataset=indice,
        fila_origen=fila_origen,
        idds=idds,
        campo=campo,
        codigo=codigo,
        mensaje=mensaje,
        valor=valor,
    )


def _referencia_legible(indice, fila_origen):
    if fila_origen is not None:
        return f"fila {fila_origen}"
    return f"registro {indice + 1}"


def _unir_referencias(referencias):
    if len(referencias) == 2:
        return " y ".join(referencias)
    return ", ".join(referencias[:-1]) + f" y {referencias[-1]}"


def _valor_seguro(valor):
    if valor is None:
        return "<vacío>"
    texto = str(valor).replace("\r", " ").replace("\n", " ")
    if len(texto) > 80:
        texto = texto[:77] + "..."
    return f'"{texto}"'
