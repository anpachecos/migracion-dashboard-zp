"""Mapeo de filas de un cursor Oracle a diccionarios.

Centraliza la conversion de las filas de `cursor.fetchone()` / `cursor.fetchall()`
en `dict`, tomando `cursor.description` como fuente de los nombres de columna.
Habia dieciseis copias de este patron, con dos variantes distintas.

`minusculas` es obligatorio a proposito. Los repositorios no coinciden en la
convencion: la mayoria espera claves en minusculas (`am_id`, `nivel_alerta`),
pero el flujo GPS y las tablas de validadores dependen de las columnas tal como
las define Oracle, en mayusculas (`AMID`, `DRIVERID`). Dejar el parametro
opcional haria que cada llamada nueva quedara a un paso de perder una u otra.
"""

def _nombres_columnas(cursor, *, minusculas):
    """Extrae los nombres de columna del cursor, en la convencion pedida.

    No se descartan entradas malformadas a proposito. `description` y la fila
    se corresponden por posicion, asi que filtrar una columna desalinearia el
    resto y devolveria datos incorrectos sin avisar. Si la descripcion viene
    rara, es preferible que reviente aca y no tres capas mas arriba.
    """
    columnas = [col[0] for col in cursor.description]
    return [col.lower() for col in columnas] if minusculas else columnas


def mapear_registro(cursor, fila, *, minusculas):
    """Mapea una fila ya traida del cursor a dict."""
    return dict(zip(_nombres_columnas(cursor, minusculas=minusculas), fila))


def mapear_fila(cursor, *, minusculas):
    """Devuelve la primera fila como dict, o None si no hay filas."""
    fila = cursor.fetchone()
    if not fila:
        return None
    return mapear_registro(cursor, fila, minusculas=minusculas)


def mapear_filas(cursor, *, minusculas):
    """Devuelve todas las filas del cursor como lista de dict."""
    columnas = _nombres_columnas(cursor, minusculas=minusculas)
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
