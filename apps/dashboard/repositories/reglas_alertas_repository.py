from decimal import Decimal, InvalidOperation
import uuid

from apps.dashboard.services import oracle_connection
from apps.dashboard.services import oracle_cursor


PROCEDIMIENTOS_RECALCULO = {
    "rapido": "USR_LAB.PRC_RECLASIFICAR_ALERTAS",
    "completo": "USR_LAB.PRC_RECALCULAR_ALERTAS_SEGURO",
}


def obtener_reglas(claves_ordenadas):
    placeholders = ", ".join(
        f":clave_{i}" for i in range(1, len(claves_ordenadas) + 1)
    )
    query = f"""
            SELECT CLAVE, VALOR_NUMERO, DESCRIPCION, ACTIVO,
                   FECHA_ACTUALIZACION, TIPO_REGLA
            FROM USR_LAB.ALERTA_REGLA_PARAM
            WHERE CLAVE IN ({placeholders})
            ORDER BY CLAVE
        """

    parametros = {
        f"clave_{i}": clave
        for i, clave in enumerate(claves_ordenadas, start=1)
    }

    with oracle_connection.obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, parametros)
            return oracle_cursor.mapear_filas(cursor, minusculas=True)


def _normalizar_valor_persistido(valor):
    if valor is None or valor == "":
        raise ValueError("El valor no puede estar vacío.")

    try:
        valor_decimal = Decimal(str(valor))
        if not valor_decimal.is_finite():
            raise ValueError
        return valor_decimal
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Valor inválido: {valor}") from exc


def actualizar_reglas(actualizaciones, tipos_permitidos):
    claves = [clave for clave, _valor in actualizaciones]
    placeholders = ", ".join(
        f":clave_{i}" for i in range(1, len(claves) + 1)
    )
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

    with oracle_connection.obtener_conexion_oracle() as conexion:
        try:
            with conexion.cursor() as cursor:
                cursor.execute(query_actuales, parametros_claves)
                reglas_actuales = {
                    fila[0]: {
                        "valor": _normalizar_valor_persistido(fila[1]),
                        "tipo": str(fila[2]).upper(),
                    }
                    for fila in cursor.fetchall()
                }

                claves_faltantes = sorted(set(claves) - set(reglas_actuales))
                if claves_faltantes:
                    raise RuntimeError(
                        "No existen en Oracle las reglas: "
                        + ", ".join(claves_faltantes)
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
                        if tipo not in tipos_permitidos
                    }
                )
                if tipos_invalidos:
                    raise RuntimeError(
                        "Hay reglas con un tipo no reconocido: "
                        + ", ".join(tipos_invalidos)
                    )

                for clave, valor_numero, _tipo in cambios:
                    cursor.execute(
                        query_actualizar,
                        {"valor_numero": valor_numero, "clave": clave},
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError(
                            f"No se pudo actualizar la regla {clave}."
                        )

                if cambios:
                    cursor.execute(
                        "BEGIN USR_LAB.PRC_VALIDAR_REGLAS_ALERTA; END;"
                    )

            conexion.commit()
        except Exception:
            conexion.rollback()
            raise

    return cambios


def obtener_procedimiento_recalculo(modo_recalculo):
    try:
        return PROCEDIMIENTOS_RECALCULO[modo_recalculo]
    except KeyError as exc:
        raise ValueError(
            f"Modo de recálculo no permitido: {modo_recalculo}"
        ) from exc


def recalcular_alertas(modo_recalculo):
    procedimiento = obtener_procedimiento_recalculo(modo_recalculo)

    with oracle_connection.obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(f"BEGIN {procedimiento}; END;")
        conexion.commit()


def crear_solicitud_recalculo(modo_recalculo, usuario_solicitante):
    """Registra una solicitud durable sin ejecutar el recálculo."""
    obtener_procedimiento_recalculo(modo_recalculo)
    solicitud_id = uuid.uuid4().hex.upper()
    modo_oracle = modo_recalculo.upper()
    usuario = (usuario_solicitante or "SISTEMA").strip() or "SISTEMA"
    query = """
        INSERT INTO USR_LAB.ALERTA_RECALCULO_SOLICITUD (
            SOLICITUD_ID,
            ORIGEN,
            MODO,
            ESTADO,
            USUARIO_SOLICITANTE,
            FECHA_SOLICITUD,
            INTENTOS,
            FECHA_ACTUALIZACION
        ) VALUES (
            :solicitud_id,
            'DJANGO_PANEL',
            :modo,
            'PENDIENTE',
            :usuario_solicitante,
            SYSTIMESTAMP,
            0,
            SYSTIMESTAMP
        )
    """
    parametros = {
        "solicitud_id": solicitud_id,
        "modo": modo_oracle,
        "usuario_solicitante": usuario[:128],
    }

    with oracle_connection.obtener_conexion_oracle() as conexion:
        try:
            with conexion.cursor() as cursor:
                cursor.execute(query, parametros)
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise

    return {
        "solicitud_id": solicitud_id,
        "origen": "DJANGO_PANEL",
        "modo": modo_oracle,
        "estado": "PENDIENTE",
        "usuario_solicitante": usuario[:128],
    }


def obtener_estado_solicitud_recalculo(solicitud_id):
    """Consulta el estado durable sin alterar la solicitud."""
    query = """
        SELECT
            SOLICITUD_ID,
            ORIGEN,
            MODO,
            ESTADO,
            USUARIO_SOLICITANTE,
            FECHA_SOLICITUD,
            FECHA_INICIO,
            FECHA_FIN,
            INTENTOS,
            OWNER_TOKEN,
            LEASE_VERSION,
            ERROR_CODIGO,
            ERROR_MENSAJE,
            FECHA_ACTUALIZACION
        FROM USR_LAB.ALERTA_RECALCULO_SOLICITUD
        WHERE SOLICITUD_ID = :solicitud_id
    """

    with oracle_connection.obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, {"solicitud_id": solicitud_id})
            return oracle_cursor.mapear_fila(cursor, minusculas=True)
