from datetime import timedelta

from django.utils import timezone


def formatear_duracion(delta):
    """
    Convierte un timedelta en texto corto.
    Ejemplo: 1h 30m
    """

    total_minutos = int(delta.total_seconds() // 60)
    horas = total_minutos // 60
    minutos = total_minutos % 60

    if horas > 0:
        return f"{horas}h {minutos}m"

    return f"{minutos}m"


def preparar_puntos_bateria_desde_registros(registros):
    """
    Convierte registros del modelo EstadoValidadorLimpio en una lista simple
    de puntos de batería ordenables.

    Usa fecha_hora como referencia principal, porque es la misma fecha usada
    en la tabla del panel de baterías.
    """

    puntos = []

    for registro in registros:
        valor = registro.porcentaje_bateria

        if valor is None or valor == "":
            continue

        fecha = registro.fecha_hora or registro.fec_estado

        if not fecha:
            continue

        try:
            bateria = float(valor)
        except (ValueError, TypeError):
            continue

        puntos.append({
            "amid": registro.amid,
            "fecha_hora": fecha,
            "fec_descarga": registro.fec_descarga,
            "fec_estado": registro.fec_estado,
            "bateria": bateria,
            "latitud": registro.latitud,
            "longitud": registro.longitud,
        })

    return sorted(
        puntos,
        key=lambda item: (str(item["amid"]), item["fecha_hora"])
    )


def detectar_caidas_drasticas_desde_puntos(
    puntos,
    umbral_caida=30,
    ventana_horas=2,
    ventana_confirmacion_minutos=60
):
    """
    Detecta caídas drásticas desde una lista de puntos.

    Regla general:
    - La batería baja al menos `umbral_caida` puntos.
    - La diferencia de tiempo entre mediciones es menor o igual a `ventana_horas`.

    Regla especial para batería 0:
    - Si cae a 0 y luego vuelve rápido a un valor normal, se considera posible error de transmisión.
    - Si cae a 0 y se mantiene en 0, sigue baja, o no vuelve a transmitir dentro de la ventana de confirmación,
      se considera caída drástica.
    """

    caidas = []
    ventana_maxima = timedelta(hours=ventana_horas)
    ventana_confirmacion = timedelta(minutes=ventana_confirmacion_minutos)

    puntos = sorted(
        puntos,
        key=lambda item: (str(item.get("amid", "")), item["fecha_hora"])
    )

    puntos_por_amid = {}

    for punto in puntos:
        amid = str(punto.get("amid", ""))
        puntos_por_amid.setdefault(amid, []).append(punto)

    for amid, puntos_amid in puntos_por_amid.items():
        for indice, actual in enumerate(puntos_amid):
            if indice == 0:
                continue

            anterior = puntos_amid[indice - 1]

            bateria_anterior = anterior["bateria"]
            bateria_actual = actual["bateria"]

            tiempo_transcurrido = actual["fecha_hora"] - anterior["fecha_hora"]
            caida = bateria_anterior - bateria_actual

            if tiempo_transcurrido <= timedelta(0):
                continue

            if tiempo_transcurrido > ventana_maxima:
                continue

            if caida < umbral_caida:
                continue

            if bateria_actual == 0:
                if es_cero_probablemente_transitorio(
                    puntos=puntos_amid,
                    indice_actual=indice,
                    bateria_anterior=bateria_anterior,
                    umbral_caida=umbral_caida,
                    ventana_confirmacion=ventana_confirmacion
                ):
                    continue

            caidas.append({
                "amid": amid,
                "fecha_hora": actual["fecha_hora"],
                "fecha_actual": actual["fecha_hora"],
                "fecha_anterior": anterior["fecha_hora"],
                "bateria_anterior": bateria_anterior,
                "bateria_actual": bateria_actual,
                "caida": caida,
                "tiempo_transcurrido": formatear_duracion(tiempo_transcurrido),
                "fec_descarga": actual.get("fec_descarga"),
                "fec_estado": actual.get("fec_estado"),
                "latitud": actual.get("latitud"),
                "longitud": actual.get("longitud"),
            })

    return caidas


def es_cero_probablemente_transitorio(
    puntos,
    indice_actual,
    bateria_anterior,
    umbral_caida,
    ventana_confirmacion
):
    """
    Revisa si una batería 0 parece error de transmisión.

    Ejemplo que NO debería ser alerta:
    70 -> 0 -> 64

    Ejemplos que SÍ deberían ser alerta:
    70 -> 0 -> 0
    70 -> 0 -> 20
    70 -> 0 -> sin nueva transmisión cercana
    """

    punto_cero = puntos[indice_actual]
    fecha_cero = punto_cero["fecha_hora"]

    puntos_posteriores_cercanos = []

    for siguiente in puntos[indice_actual + 1:]:
        diferencia = siguiente["fecha_hora"] - fecha_cero

        if diferencia <= timedelta(0):
            continue

        if diferencia > ventana_confirmacion:
            break

        puntos_posteriores_cercanos.append(siguiente)

    # Si no volvió a transmitir pronto, se considera alerta.
    if not puntos_posteriores_cercanos:
        return False

    # Si vuelve a marcar 0 dentro de la ventana, se confirma alerta.
    for punto in puntos_posteriores_cercanos:
        if punto["bateria"] == 0:
            return False

    primer_punto_posterior = puntos_posteriores_cercanos[0]
    bateria_posterior = primer_punto_posterior["bateria"]

    caida_real_posterior = bateria_anterior - bateria_posterior

    # Si después del 0 vuelve a un valor cercano al anterior,
    # probablemente fue error de transmisión.
    if bateria_posterior > 0 and caida_real_posterior < umbral_caida:
        return True

    # Si después del 0 sigue con una caída grande, se mantiene como alerta.
    return False