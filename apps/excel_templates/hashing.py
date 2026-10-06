"""
Hash determinista para deduplicar estilos.

La deduplicacion depende de esto: el mismo Excel debe producir siempre los
mismos hashes, y dos estilos visualmente iguales deben colapsar en el mismo
registro. Se serializa a JSON con claves ordenadas y `ensure_ascii=False`
para que un texto con acentos no genere un hash distinto al mismo texto sin
ellos.
"""

import hashlib
import json
from datetime import date, datetime, time
from decimal import Decimal


def _normalizar(valor):
    """Convierte valores no serializables a algo estable."""

    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor

    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()

    if isinstance(valor, Decimal):
        # 12.0 y 12 deben colapsar: Excel no distingue uno de otro.
        return float(valor)

    if isinstance(valor, dict):
        return {str(k): _normalizar(v) for k, v in sorted(valor.items(), key=lambda p: str(p[0]))}

    if isinstance(valor, (list, tuple, set)):
        return [_normalizar(v) for v in valor]

    return str(valor)


def hash_de(valor):
    """Devuelve el hash SHA-256 (hex, 64 chars) de cualquier estructura."""

    texto = json.dumps(
        _normalizar(valor),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def sha256_archivo(ruta, bloque=1024 * 1024):
    """SHA-256 de un archivo leido por bloques (para archivos grandes)."""

    digest = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        while True:
            datos = archivo.read(bloque)
            if not datos:
                break
            digest.update(datos)
    return digest.hexdigest()


def sha256_bytes(datos):
    """SHA-256 de un contenido en memoria."""

    return hashlib.sha256(datos).hexdigest()