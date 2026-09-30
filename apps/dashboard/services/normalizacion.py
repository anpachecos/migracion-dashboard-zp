from django.utils import timezone


def obtener_ahora_referencia():
    """
    Retorna la fecha/hora actual sin tzinfo para comparar con fechas Oracle.
    Oracle ya entrega las fechas en la hora correcta, por eso evitamos conversiones
    que puedan generar desfase.
    """
    ahora = timezone.localtime(timezone.now())

    if timezone.is_aware(ahora):
        return timezone.make_naive(ahora)

    return ahora


def normalizar_fecha_para_comparar(fecha):
    """
    Evita errores al comparar/restar fechas aware vs naive.
    No cambia la hora funcional, solo quita tzinfo si existe.
    """
    if not fecha:
        return None

    if timezone.is_aware(fecha):
        return timezone.make_naive(fecha)

    return fecha


def normalizar_booleano_oracle(valor):
    """
    Normaliza valores booleanos que pueden venir desde Oracle como:
    1/0, true/false, TRUE/FALSE, Sí/No, etc.

    Contrato: devuelve True, False o None.
    None indica "sin dato" (valor vacío o no reconocido).
    """
    if valor is None:
        return None

    if isinstance(valor, bool):
        return valor

    if isinstance(valor, (int, float)):
        if valor in (0, 1):
            return valor == 1

        return None

    texto = str(valor).strip().lower()

    if texto in ["true", "1", "si", "sí", "s", "yes", "y"]:
        return True

    if texto in ["false", "0", "no", "n"]:
        return False

    return None


def convertir_numero(valor):
    """
    Convierte valores numéricos Oracle/Python a float.
    """
    if valor is None or valor == "":
        return None

    try:
        return float(valor)
    except (ValueError, TypeError):
        return None