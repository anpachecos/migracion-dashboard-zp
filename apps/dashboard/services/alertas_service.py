from datetime import timedelta

from django.db.models import Count, Min, Max
from django.utils import timezone

from apps.dashboard.models import EstadoValidadorLimpio


def clasificar_gps_cero(cantidad_registros):
    if cantidad_registros >= 5:
        return "Frecuente"

    if cantidad_registros >= 2:
        return "Repetido"

    return "Aislado"



def obtener_alertas_gps_cero(dias=1, mostrar_todo=False):
    """
    Obtiene resumen de AMIDs únicos con GPS 0 dentro del período seleccionado.

    Regla:
    - latitud = 0
    - longitud = 0
    """

    try:
        dias = int(dias)
    except ValueError:
        dias = 1

    if dias not in [1, 3, 7, 14]:
        dias = 1

    fecha_inicio = timezone.now() - timedelta(days=dias)

    registros_gps_cero = (
        EstadoValidadorLimpio.objects
        .filter(
            fec_estado__gte=fecha_inicio,
            latitud=0,
            longitud=0,
        )
    )

    total_registros_gps_cero = registros_gps_cero.count()

    resumen_por_amid = (
        registros_gps_cero
        .values("amid")
        .annotate(
            cantidad_registros=Count("id"),
            primera_deteccion=Min("fec_estado"),
            ultima_deteccion=Max("fec_estado"),
        )
        .order_by("-cantidad_registros", "-ultima_deteccion")
    )

    total_amids_gps_cero = resumen_por_amid.count()

    if mostrar_todo:
        resumen_visible = list(resumen_por_amid)
    else:
        resumen_visible = list(resumen_por_amid[:5])

    for item in resumen_visible:
        ultimo_registro = (
            registros_gps_cero
            .filter(
                amid=item["amid"],
                fec_estado=item["ultima_deteccion"],
            )
            .order_by("-id")
            .first()
        )

        item["ultima_bateria"] = (
            ultimo_registro.porcentaje_bateria
            if ultimo_registro
            else None
        )

        item["estado_alerta"] = clasificar_gps_cero(
            item["cantidad_registros"]
        )

    return {
        "dias": dias,
        "total_amids_gps_cero": total_amids_gps_cero,
        "total_registros_gps_cero": total_registros_gps_cero,
        "resumen_gps_cero": resumen_visible,
        "mostrar_todo": mostrar_todo,
        "hay_mas_registros": total_amids_gps_cero > 5,
    }