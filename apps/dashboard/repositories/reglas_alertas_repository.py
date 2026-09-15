from decimal import Decimal, InvalidOperation

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


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

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, parametros)
            columnas = [col[0].lower() for col in cursor.description]
            return [
                dict(zip(columnas, fila))
                for fila in cursor.fetchall()
            ]


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

    with obtener_conexion_oracle() as conexion:
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

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(f"BEGIN {procedimiento}; END;")
        conexion.commit()
