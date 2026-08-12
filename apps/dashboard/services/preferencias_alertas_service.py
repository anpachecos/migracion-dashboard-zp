import re

from django.db import transaction

from apps.dashboard.models import AlertaAmidExcluido, AlertaUbicacionExcluida

MAX_AMIDS_EXCLUIDOS = 500
MAX_UBICACIONES_EXCLUIDAS = 200


def parsear_amids_excluidos(texto):
    """Convierte una lista separada por espacios, comas o lineas a AMID unicos."""

    tokens = [token for token in re.split(r"[\s,;]+", (texto or "").strip()) if token]
    amids = []

    for token in tokens:
        if not token.isdigit() or int(token) <= 0:
            raise ValueError(f"El valor '{token}' no es un AMID v\u00e1lido.")
        amids.append(int(token))

    amids = sorted(set(amids))
    if len(amids) > MAX_AMIDS_EXCLUIDOS:
        raise ValueError(
            f"Solo se pueden excluir hasta {MAX_AMIDS_EXCLUIDOS} AMID por usuario."
        )

    return amids


def obtener_preferencias_alertas_usuario(usuario):
    return {
        "amids_excluidos": list(
            AlertaAmidExcluido.objects.filter(usuario=usuario)
            .order_by("amid")
            .values_list("amid", flat=True)
        ),
        "ubicaciones_excluidas": list(
            AlertaUbicacionExcluida.objects.filter(usuario=usuario)
            .order_by("nombre")
            .values_list("nombre", flat=True)
        ),
    }


@transaction.atomic
def guardar_preferencias_alertas_usuario(
    usuario,
    texto_amids,
    ubicaciones,
    ubicaciones_disponibles,
):
    """Reemplaza de forma atomica las exclusiones del usuario en SQLite."""

    amids = parsear_amids_excluidos(texto_amids)
    ubicaciones = sorted(
        {str(nombre).strip() for nombre in (ubicaciones or []) if str(nombre).strip()}
    )

    if len(ubicaciones) > MAX_UBICACIONES_EXCLUIDAS:
        raise ValueError("Se seleccionaron demasiadas ubicaciones para excluir.")

    disponibles = set(ubicaciones_disponibles)
    no_disponibles = [nombre for nombre in ubicaciones if nombre not in disponibles]
    if no_disponibles:
        raise ValueError(
            "Una o m\u00e1s ubicaciones ya no est\u00e1n disponibles. "
            "Recarga el panel e int\u00e9ntalo nuevamente."
        )

    AlertaAmidExcluido.objects.filter(usuario=usuario).delete()
    AlertaUbicacionExcluida.objects.filter(usuario=usuario).delete()

    AlertaAmidExcluido.objects.bulk_create(
        [AlertaAmidExcluido(usuario=usuario, amid=amid) for amid in amids]
    )
    AlertaUbicacionExcluida.objects.bulk_create(
        [
            AlertaUbicacionExcluida(usuario=usuario, nombre=nombre)
            for nombre in ubicaciones
        ]
    )

    return {
        "amids_excluidos": amids,
        "ubicaciones_excluidas": ubicaciones,
    }