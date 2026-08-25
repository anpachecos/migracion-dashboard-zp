import re
from datetime import datetime, time

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


PATRON_INTERVALO = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*[-\u2013\u2014]\s*(\d{1,2}):(\d{2})\s*$"
)
NOMBRES_DIAS = (
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
)
CAMPOS_HORARIO = (
    ("HORARIO", "Horario AM"),
    ("HORARIO_LABORAL_PM", "Horario laboral PM"),
    ("HORARIO_SABADO", "Horario sábado"),
    ("HORARIO_DOMINGO", "Horario domingo"),
)


def _obtener_valor(datos, clave):
    if not datos:
        return None
    if isinstance(datos, dict):
        return datos.get(clave) or datos.get(clave.lower())
    return getattr(datos, clave, None) or getattr(datos, clave.lower(), None)


def parsear_intervalo_horario(valor):
    """Convierte HH:MM - HH:MM en horas comparables, o None si no es seguro."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto or texto in {"-", "—"}:
        return None
    coincidencia = PATRON_INTERVALO.match(texto)
    if not coincidencia:
        return None
    try:
        hora_inicio = time(int(coincidencia.group(1)), int(coincidencia.group(2)))
        hora_fin = time(int(coincidencia.group(3)), int(coincidencia.group(4)))
    except ValueError:
        return None
    return {
        "inicio": hora_inicio,
        "fin": hora_fin,
        "texto": f"{hora_inicio.strftime('%H:%M')} a {hora_fin.strftime('%H:%M')}",
    }


def _claves_para_dia(fecha):
    if fecha.weekday() <= 4:
        return ("HORARIO", "HORARIO_LABORAL_PM")
    if fecha.weekday() == 5:
        return ("HORARIO_SABADO",)
    return ("HORARIO_DOMINGO",)


def obtener_intervalos_para_fecha(configuracion, fecha):
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    if not fecha or not configuracion:
        return []
    intervalos = configuracion.get("intervalos_por_clave", {})
    return [
        intervalos[clave]
        for clave in _claves_para_dia(fecha)
        if intervalos.get(clave)
    ]


def crear_configuracion_horario_zp(datos=None, fecha_referencia=None):
    """Prepara una única estructura para mostrar y aplicar horarios vigentes."""
    fecha_referencia = fecha_referencia or datetime.now()
    fecha_hoy = (
        fecha_referencia.date()
        if isinstance(fecha_referencia, datetime)
        else fecha_referencia
    )
    items = []
    intervalos_por_clave = {}
    hay_valor_configurado = False

    for clave, etiqueta in CAMPOS_HORARIO:
        valor_original = _obtener_valor(datos, clave)
        texto_original = str(valor_original).strip() if valor_original is not None else ""
        intervalo = parsear_intervalo_horario(texto_original)
        if texto_original and texto_original not in {"-", "—"}:
            hay_valor_configurado = True
        if intervalo:
            intervalos_por_clave[clave] = intervalo
        items.append({
            "clave": clave,
            "etiqueta": etiqueta,
            "valor": intervalo["texto"] if intervalo else (texto_original or "—"),
            "valido": intervalo is not None,
        })

    configuracion = {
        "items": items,
        "intervalos_por_clave": intervalos_por_clave,
        "dia_hoy": NOMBRES_DIAS[fecha_hoy.weekday()],
        "ubicacion": _obtener_valor(datos, "NOMBRE") or "Sin ubicación asignada",
        "tiene_configuracion": hay_valor_configurado,
        "tiene_horario_hoy": False,
        "texto_hoy": "Sin horario asignado",
        "mensaje_hoy": "",
    }
    intervalos_hoy = obtener_intervalos_para_fecha(configuracion, fecha_hoy)
    configuracion["intervalos_hoy"] = intervalos_hoy
    configuracion["tiene_horario_hoy"] = bool(intervalos_hoy)
    if intervalos_hoy:
        configuracion["texto_hoy"] = " · ".join(
            intervalo["texto"] for intervalo in intervalos_hoy
        )
        configuracion["mensaje_hoy"] = (
            f"Horario aplicable hoy ({configuracion['dia_hoy']})."
        )
    else:
        configuracion["mensaje_hoy"] = (
            f"No tiene horario asignado para hoy ({configuracion['dia_hoy']}); "
            "los datos se mantienen sin filtro."
        )
    return configuracion


def hora_esta_en_intervalos(hora_registro, intervalos):
    """Comprueba la hora y admite intervalos que crucen medianoche."""
    for intervalo in intervalos:
        inicio = intervalo["inicio"]
        fin = intervalo["fin"]
        if inicio <= fin and inicio <= hora_registro <= fin:
            return True
        if inicio > fin and (hora_registro >= inicio or hora_registro <= fin):
            return True
    return False


def filtrar_registros_por_horario_zp(
    registros, configuracion, atributo_fecha="fecha_registro",
):
    """Filtra por cada día; si ese día no tiene horario, conserva sus filas."""
    registros_filtrados = []
    fechas_con_horario = set()
    for registro in registros:
        fecha_hora = getattr(registro, atributo_fecha, None)
        if fecha_hora is None and atributo_fecha != "fecha_hora":
            fecha_hora = getattr(registro, "fecha_hora", None)
        if not fecha_hora:
            registros_filtrados.append(registro)
            continue
        intervalos = obtener_intervalos_para_fecha(configuracion, fecha_hora)
        if not intervalos:
            registros_filtrados.append(registro)
            continue
        fechas_con_horario.add(fecha_hora.date())
        if hora_esta_en_intervalos(fecha_hora.time(), intervalos):
            registros_filtrados.append(registro)
    return registros_filtrados, bool(fechas_con_horario)


def obtener_columnas_media_hora_para_hoy(configuracion):
    """Devuelve bloques de 30 minutos incluidos en el horario vigente de hoy."""
    intervalos = configuracion.get("intervalos_hoy", []) if configuracion else []
    if not intervalos:
        return []
    columnas = []
    for hora in range(24):
        for minuto in (0, 30):
            hora_bloque = time(hora, minuto)
            if hora_esta_en_intervalos(hora_bloque, intervalos):
                columnas.append(hora_bloque.strftime("%H:%M"))
    return columnas


def obtener_datos_horario_zp_oracle(amid):
    """Consulta una sola fila vigente e indexada por AMID."""
    query = """
        SELECT AMID, NOMBRE, HORARIO, HORARIO_LABORAL_PM,
               HORARIO_SABADO, HORARIO_DOMINGO
        FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
        WHERE AMID = :amid
    """
    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, {"amid": str(amid).strip()})
            fila = cursor.fetchone()
            if not fila:
                return None
            columnas = [col[0] for col in cursor.description]
            return dict(zip(columnas, fila))
