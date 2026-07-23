from __future__ import annotations

import os
import threading
from datetime import datetime

from django.conf import settings

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


def usuario_puede_editar_reglas(user):
    return user.is_superuser or user.groups.filter(name="Admin").exists()


def obtener_reglas_alertas():
    try:
        claves_ordenadas = sorted(CLAVES_PERMITIDAS_TODO)
        placeholders = ", ".join(f":clave_{i}" for i in range(1, len(claves_ordenadas) + 1))
        query = f"""
            SELECT CLAVE, VALOR_NUMERO, DESCRIPCION, ACTIVO, FECHA_ACTUALIZACION
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
                }
            )

        mapa_reglas = {regla["clave"]: regla for regla in reglas}
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


def _normalizar_valor_numero(valor):
    if valor is None or valor == "":
        raise ValueError("El valor no puede estar vacío.")

    try:
        return float(valor)
    except (TypeError, ValueError) as exc:
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

    query = """
        UPDATE USR_LAB.ALERTA_REGLA_PARAM
        SET VALOR_NUMERO = :valor_numero,
            FECHA_ACTUALIZACION = SYSDATE
        WHERE CLAVE = :clave
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            for clave, valor_numero in actualizaciones:
                cursor.execute(query, {"valor_numero": valor_numero, "clave": clave})

        conexion.commit()

    return actualizaciones


def _escribir_log_recalculo(log_path, mensaje):
    if not log_path:
        return

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as archivo:
        archivo.write(f"[{timestamp}] {mensaje}\n")


def leer_log_recalculo(log_path=None):
    if not log_path:
        log_path = os.path.join(settings.BASE_DIR, "temp_uploads", "alertas_recalculo.log")

    if not os.path.exists(log_path):
        return ""

    with open(log_path, "r", encoding="utf-8") as archivo:
        contenido = archivo.read().strip()

    return contenido


def recalcular_alertas(log_path=None, log_callback=None):
    if log_callback:
        log_callback("Se inicia el recálculo de alertas en Oracle.")

    try:
        with obtener_conexion_oracle() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("BEGIN USR_LAB.PRC_UPD_ALERTAS_VAL; END;")
            conexion.commit()

        if log_callback:
            log_callback("Recálculo finalizado correctamente.")
        return True
    except Exception as exc:
        mensaje_error = f"No se pudo recalcular alertas: {exc}"
        if log_callback:
            log_callback(mensaje_error)
        raise RuntimeError(mensaje_error) from exc


def iniciar_recalculo_en_segundo_plano(log_path=None):
    if not log_path:
        log_path = os.path.join(settings.BASE_DIR, "temp_uploads", "alertas_recalculo.log")

    def worker():
        _escribir_log_recalculo(log_path, "Solicitud de recálculo enviada desde el panel.")

        try:
            recalcular_alertas(
                log_path=log_path,
                log_callback=lambda mensaje: _escribir_log_recalculo(log_path, mensaje),
            )
        except Exception as exc:
            _escribir_log_recalculo(log_path, str(exc))

    hilo = threading.Thread(target=worker, daemon=True, name="recalculo-alertas")
    hilo.start()
    return hilo
