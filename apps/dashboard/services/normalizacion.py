import unicodedata

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


def normalizar_numero(valor, default=0):
    if valor is None:
        return default

    return valor


def normalizar_texto(valor, default=""):
    if valor is None:
        return default

    return str(valor)


def normalizar_texto_sin_acentos(valor):
    """
    Normaliza texto para búsquedas y comparaciones sin importar acentos,
    mayúsculas ni espacios: NFKD + minúsculas + quita signos diacríticos.
    """
    texto = unicodedata.normalize("NFKD", str(valor or "").strip().lower())

    return "".join(caracter for caracter in texto if not unicodedata.combining(caracter))


def es_coordenada_cero(latitud, longitud):
    """
    Detecta pares de coordenadas 0,0 compartidos por GPS y exportaciones.

    None o valores no numéricos no son "0,0". Contrato: devuelve bool.
    """
    if latitud is None or longitud is None:
        return False

    try:
        return float(latitud) == 0 and float(longitud) == 0
    except (ValueError, TypeError):
        return False


def obtener_fecha(valor):
    """
    Devuelve solo la fecha, sin aplicar timezone.localtime().
    """
    if not valor:
        return None

    valor = normalizar_fecha_para_comparar(valor)
    return valor.date()


def convertir_entero(valor, defecto=0):
    """
    Convierte valores numéricos Oracle/Python a int.
    """
    numero = convertir_numero(valor)

    if numero is None:
        return defecto

    return int(numero)
