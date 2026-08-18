from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.cache import cache

from apps.dashboard.services.catalogo_reglas_alertas import (
    construir_editor_reglas_alertas,
    validar_catalogo_reglas,
)
from apps.dashboard.services.oracle_connection import obtener_conexion_oracle

CLAVES_PERMITIDAS = {
    "GPS": [
        "GPS_CERO_HOY_CRITICA",
        "GPS_PORC_HOY_CRITICA",
        "GPS_TOTAL_HOY_CRITICA",
        "GPS_RACHA_CRITICA",
        "GPS_CERO_HOY_ALTA",
        "GPS_CERO_HOY_ALTA_MAX",
        "GPS_PORC_HOY_ALTA",
        "GPS_TOTAL_HOY_ALTA",
        "GPS_RACHA_ALTA",
        "GPS_CERO_HOY_ADV",
        "GPS_CERO_HOY_ADV_MAX",
        "GPS_CERO_HIST_ADV",
        "GPS_PORC_HIST_ADV",
    ],
    "BATERIA": [
        "BAT_CAIDA_MIN_DETECTAR",
        "BAT_CAIDA_MAX_HORAS",
        "BAT_CAIDA_HOY_CRITICA",
        "BAT_CAIDA_HOY_CRITICA_CON_HIST",
        "BAT_CAIDAS_HOY_CRITICA",
        "BAT_CERO_HOY_CRITICA",
        "BAT_CAIDA_HOY_ALTA",
        "BAT_CAIDAS_HIST_ALTA",
        "BAT_CAIDA_MAX_HIST_ALTA",
        "BAT_CERO_HOY_ALTA_MIN",
        "BAT_CERO_HOY_ALTA_MAX",
        "BAT_CERO_HOY_ADV_MIN",
        "BAT_CERO_HOY_ADV_MAX",
        "BAT_CERO_HIST_ADV",
    ],
}

CLAVES_PERMITIDAS_TODO = set(CLAVES_PERMITIDAS["GPS"]) | set(CLAVES_PERMITIDAS["BATERIA"])
validar_catalogo_reglas(CLAVES_PERMITIDAS_TODO)

CACHE_KEY_RESUMEN_ALERTAS = "dashboard:resumen-alertas-activos:v1"

LOG_RECALCULO_MAX_BYTES = 1024 * 1024
LOG_RECALCULO_LINEAS_VISIBLES = 100

_recalculo_lock = threading.Lock()
_log_recalculo_lock = threading.Lock()

PROCEDIMIENTOS_RECALCULO = {
    "rapido": "USR_LAB.PRC_RECLASIFICAR_ALERTAS",
    "completo": "USR_LAB.PRC_RECALCULAR_ALERTAS_SEGURO",
}


def usuario_puede_editar_reglas(user):
    return user.is_superuser or user.groups.filter(name="Admin").exists()


def obtener_reglas_alertas():
    try:
        claves_ordenadas = sorted(CLAVES_PERMITIDAS_TODO)
        placeholders = ", ".join(f":clave_{i}" for i in range(1, len(claves_ordenadas) + 1))
        query = f"""
            SELECT CLAVE, VALOR_NUMERO, DESCRIPCION, ACTIVO,
                   FECHA_ACTUALIZACION, TIPO_REGLA
            FROM USR_LAB.ALERTA_REGLA_PARAM
            WHERE CLAVE IN ({placeholders})
            ORDER BY CLAVE
        """

        parametros = {f"clave_{i}": clave for i, clave in enumerate(claves_ordenadas, start=1)}

        with obtener_conexion_oracle() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(query, parametros)
                columnas = [col[0].lower() for col in cursor.description]
                filas = cursor.fetchall()

        reglas = []
        for fila in filas:
            datos = dict(zip(columnas, fila))
            valor_numero = datos.get("valor_numero")
            if valor_numero is None:
                valor_numero = datos.get("valor")

            reglas.append(
                {
                    "clave": datos.get("clave"),
                    "valor_numero": valor_numero,
                    "descripcion": datos.get("descripcion") or "",
                    "activo": datos.get("activo"),
                    "fecha_actualizacion": datos.get("fecha_actualizacion"),
                    "tipo_regla": datos.get("tipo_regla"),
                }
            )

        mapa_reglas = {regla["clave"]: regla for regla in reglas}
        claves_faltantes = CLAVES_PERMITIDAS_TODO - set(mapa_reglas)
        if claves_faltantes:
            raise RuntimeError(
                "Faltan reglas configurables en ALERTA_REGLA_PARAM: "
                + ", ".join(sorted(claves_faltantes))
            )

        resultado = {
            "GPS": [],
            "BATERIA": [],
        }

        for clave in CLAVES_PERMITIDAS["GPS"]:
            if clave in mapa_reglas:
                resultado["GPS"].append(mapa_reglas[clave])

        for clave in CLAVES_PERMITIDAS["BATERIA"]:
            if clave in mapa_reglas:
                resultado["BATERIA"].append(mapa_reglas[clave])

        return resultado
    except Exception as exc:
        raise RuntimeError(f"No fue posible cargar las reglas de alertas desde Oracle: {exc}") from exc


def obtener_editor_reglas_alertas():
    """Carga una sola vez los valores Oracle y agrega metadatos para la interfaz."""
    return construir_editor_reglas_alertas(obtener_reglas_alertas())


def _normalizar_valor_numero(valor):
    if valor is None or valor == "":
        raise ValueError("El valor no puede estar vacío.")

    try:
        valor_decimal = Decimal(str(valor))
        if not valor_decimal.is_finite():
            raise ValueError
        return valor_decimal
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Valor inválido: {valor}") from exc


def actualizar_reglas_alertas(reglas_form):
    if not reglas_form:
        raise ValueError("No se recibieron reglas para actualizar.")

    actualizaciones = []

    for nombre, valor in reglas_form.items():
        if not nombre.startswith("regla_"):
            continue

        clave = nombre.replace("regla_", "")
        if clave not in CLAVES_PERMITIDAS_TODO:
            raise ValueError(f"Clave no permitida: {clave}")

        valor_numero = _normalizar_valor_numero(valor)
        actualizaciones.append((clave, valor_numero))

    if not actualizaciones:
        raise ValueError("No se encontraron reglas válidas en el formulario.")

    claves = [clave for clave, _valor in actualizaciones]
    placeholders = ", ".join(f":clave_{i}" for i in range(1, len(claves) + 1))
    parametros_claves = {
        f"clave_{i}": clave
        for i, clave in enumerate(claves, start=1)
    }

    query_actuales = f"""
        SELECT CLAVE, VALOR_NUMERO, TIPO_REGLA
        FROM USR_LAB.ALERTA_REGLA_PARAM
        WHERE CLAVE IN ({placeholders})
        FOR UPDATE
    """

    query_actualizar = """
        UPDATE USR_LAB.ALERTA_REGLA_PARAM
        SET VALOR_NUMERO = :valor_numero,
            FECHA_ACTUALIZACION = SYSDATE
        WHERE CLAVE = :clave
    """

    with obtener_conexion_oracle() as conexion:
        try:
            with conexion.cursor() as cursor:
                cursor.execute(query_actuales, parametros_claves)
                reglas_actuales = {
                    fila[0]: {
                        "valor": _normalizar_valor_numero(fila[1]),
                        "tipo": str(fila[2]).upper(),
                    }
                    for fila in cursor.fetchall()
                }

                claves_faltantes = sorted(set(claves) - set(reglas_actuales))
                if claves_faltantes:
                    raise RuntimeError(
                        "No existen en Oracle las reglas: " + ", ".join(claves_faltantes)
                    )

                cambios = [
                    (clave, valor_numero, reglas_actuales[clave]["tipo"])
                    for clave, valor_numero in actualizaciones
                    if reglas_actuales[clave]["valor"] != valor_numero
                ]

                tipos_invalidos = sorted(
                    {
                        tipo
                        for _clave, _valor, tipo in cambios
                        if tipo not in {"DETECCION", "CLASIFICACION"}
                    }
                )
                if tipos_invalidos:
                    raise RuntimeError(
                        "Hay reglas con un tipo no reconocido: " + ", ".join(tipos_invalidos)
                    )

                for clave, valor_numero, _tipo in cambios:
                    cursor.execute(
                        query_actualizar,
                        {"valor_numero": valor_numero, "clave": clave},
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError(f"No se pudo actualizar la regla {clave}.")

                if cambios:
                    # Se valida dentro de la misma transacción: si la combinación
                    # de umbrales es incoherente, Oracle falla y todo se revierte.
                    cursor.execute("BEGIN USR_LAB.PRC_VALIDAR_REGLAS_ALERTA; END;")

            conexion.commit()
        except Exception:
            conexion.rollback()
            raise

    modo_recalculo = None
    if cambios:
        modo_recalculo = (
            "completo"
            if any(tipo == "DETECCION" for _clave, _valor, tipo in cambios)
            else "rapido"
        )

    return {
        "cantidad": len(cambios),
        "claves": [clave for clave, _valor, _tipo in cambios],
        "modo_recalculo": modo_recalculo,
    }


def _escribir_log_recalculo(log_path, mensaje):
    if not log_path:
        return

    carpeta_log = os.path.dirname(log_path)
    if carpeta_log:
        os.makedirs(carpeta_log, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with _log_recalculo_lock:
        if (
            os.path.exists(log_path)
            and os.path.getsize(log_path) >= LOG_RECALCULO_MAX_BYTES
        ):
            # Se conserva una generación anterior y se evita crecimiento infinito.
            os.replace(log_path, f"{log_path}.1")

        with open(log_path, "a", encoding="utf-8") as archivo:
            archivo.write(f"[{timestamp}] {mensaje}\n")


def leer_log_recalculo(log_path=None, max_lineas=LOG_RECALCULO_LINEAS_VISIBLES):
    if not log_path:
        log_path = os.path.join(settings.BASE_DIR, "temp_uploads", "alertas_recalculo.log")

    if not os.path.exists(log_path):
        return ""

    with open(log_path, "r", encoding="utf-8", errors="replace") as archivo:
        lineas = archivo.readlines()

    return "".join(lineas[-max_lineas:]).strip()


def recalculo_en_curso():
    """Estado local: cubre el proceso Django actual, no otros servidores."""
    return _recalculo_lock.locked()


def _obtener_procedimiento_recalculo(modo_recalculo):
    try:
        return PROCEDIMIENTOS_RECALCULO[modo_recalculo]
    except KeyError as exc:
        raise ValueError(f"Modo de recálculo no permitido: {modo_recalculo}") from exc


def recalcular_alertas(modo_recalculo="completo", log_path=None, log_callback=None):
    procedimiento = _obtener_procedimiento_recalculo(modo_recalculo)
    inicio = time.perf_counter()

    if log_callback:
        log_callback(f"Se inicia el recálculo {modo_recalculo} de alertas en Oracle.")

    try:
        with obtener_conexion_oracle() as conexion:
            with conexion.cursor() as cursor:
                # El wrapper rápido solo reclasifica métricas existentes. El
                # completo relee los datos cuando cambió una regla de detección.
                cursor.execute(f"BEGIN {procedimiento}; END;")
            conexion.commit()

        # La siguiente visita debe leer los totales recién recalculados.
        cache.delete(CACHE_KEY_RESUMEN_ALERTAS)
        duracion = time.perf_counter() - inicio

        if log_callback:
            log_callback(
                f"Recálculo {modo_recalculo} finalizado correctamente "
                f"en {duracion:.2f} segundos."
            )
        return True
    except Exception as exc:
        duracion = time.perf_counter() - inicio
        mensaje_error = (
            f"No se pudo recalcular alertas después de {duracion:.2f} segundos: {exc}"
        )
        if log_callback:
            log_callback(mensaje_error)
        raise RuntimeError(mensaje_error) from exc


def iniciar_recalculo_en_segundo_plano(modo_recalculo="completo", log_path=None):
    _obtener_procedimiento_recalculo(modo_recalculo)

    if not _recalculo_lock.acquire(blocking=False):
        return None

    if not log_path:
        log_path = os.path.join(settings.BASE_DIR, "temp_uploads", "alertas_recalculo.log")

    def worker():
        try:
            _escribir_log_recalculo(
                log_path,
                f"Solicitud de recálculo {modo_recalculo} enviada desde el panel.",
            )
            recalcular_alertas(
                modo_recalculo=modo_recalculo,
                log_path=log_path,
                log_callback=lambda mensaje: _escribir_log_recalculo(log_path, mensaje),
            )
        except Exception as exc:
            try:
                _escribir_log_recalculo(log_path, str(exc))
            except OSError:
                pass
        finally:
            _recalculo_lock.release()

    hilo = threading.Thread(
        target=worker,
        daemon=True,
        name=f"recalculo-alertas-{modo_recalculo}",
    )

    try:
        hilo.start()
    except Exception:
        _recalculo_lock.release()
        raise

    return hilo
