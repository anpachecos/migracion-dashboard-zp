from datetime import datetime, timedelta

from django.utils import timezone

from ..models import EstadoValidadorLimpio

def obtener_clase_tarjeta_bateria(valor):
    if valor is None or valor == "":
        return "tarjeta-neutra"

    try:
        valor = float(valor)
    except (ValueError, TypeError):
        return "tarjeta-neutra"

    if valor >= 80:
        return "tarjeta-ok"
    elif valor >= 50:
        return "tarjeta-warning"
    elif valor >= 20:
        return "tarjeta-warning"
    else:
        return "tarjeta-error"


def evaluar_fecha_descarga(fecha_descarga):
    if not fecha_descarga:
        return "Sin dato", "tarjeta-neutra"

    fecha_local = timezone.localtime(fecha_descarga)
    hoy = timezone.localdate()

    if fecha_local.date() == hoy:
        return "Hoy", "tarjeta-ok"

    return "No descargó hoy", "tarjeta-error"


def evaluar_fecha_estatus(fecha_estado):
    if not fecha_estado:
        return "Sin dato", "tarjeta-neutra"

    fecha_local = timezone.localtime(fecha_estado)
    ahora = timezone.localtime(timezone.now())
    hoy = timezone.localdate()

    if fecha_local.date() != hoy:
        return "Sin estatus hoy", "tarjeta-error"

    diferencia_horas = (ahora - fecha_local).total_seconds() / 3600

    if diferencia_horas <= 1:
        return "Actualizado", "tarjeta-ok"

    return "Hace más de 1 hora", "tarjeta-warning"


def evaluar_chip_booleano(valor, texto_ok="Sí", texto_error="No"):
    if valor in [True, "True", "true", "1", 1, "SI", "Sí", "S", "s", "si", "sí"]:
        return texto_ok, "chip-ok"

    if valor in [False, "False", "false", "0", 0, "NO", "No", "N", "n", "no"]:
        return texto_error, "chip-error"

    return "Sin dato", "chip-neutro"


def evaluar_error_bateria(valor):
    if valor in [True, "True", "true", "1", 1, "SI", "Sí", "S", "s", "si", "sí"]:
        return "Sí", "chip-error"

    if valor in [False, "False", "false", "0", 0, "NO", "No", "N", "n", "no"]:
        return "No", "chip-ok"

    return "Sin dato", "chip-neutro"


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


def detectar_caidas_drasticas(registros, umbral_caida=30, ventana_horas=2):
    """
    Detecta caídas drásticas de batería para un AMID.

    Regla:
    - La batería baja al menos `umbral_caida` puntos.
    - La diferencia de tiempo entre mediciones es menor o igual a `ventana_horas`.

    Ejemplo:
    70% -> 30% en 2 horas = caída drástica.
    70% -> 30% en 24 horas = no cuenta.
    """

    caidas = []
    registros_validos = []
    ventana_maxima = timedelta(hours=ventana_horas)

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

        registros_validos.append({
            "fecha_hora": fecha,
            "bateria": bateria,
        })

    registros_validos = sorted(
        registros_validos,
        key=lambda item: item["fecha_hora"]
    )

    for anterior, actual in zip(registros_validos, registros_validos[1:]):
        bateria_anterior = anterior["bateria"]
        bateria_actual = actual["bateria"]

        tiempo_transcurrido = actual["fecha_hora"] - anterior["fecha_hora"]
        caida = bateria_anterior - bateria_actual

        if (
            tiempo_transcurrido > timedelta(0)
            and tiempo_transcurrido <= ventana_maxima
            and caida >= umbral_caida
        ):
            caidas.append({
                "fecha_hora": actual["fecha_hora"],
                "fecha_anterior": anterior["fecha_hora"],
                "bateria_anterior": bateria_anterior,
                "bateria_actual": bateria_actual,
                "caida": caida,
                "tiempo_transcurrido": formatear_duracion(tiempo_transcurrido),
            })

    return caidas


def obtener_contexto_baterias(request):
    amid = request.GET.get("amid", "").strip()
    dias = request.GET.get("dias", "14")
    hora_inicio = request.GET.get("hora_inicio", "00:00")
    hora_fin = request.GET.get("hora_fin", "23:30")
    usar_sugerido = request.GET.get("usar_sugerido", "")

    try:
        dias = int(dias)
    except ValueError:
        dias = 14

    if dias not in [1, 3, 7, 14]:
        dias = 14

    if not hora_inicio:
        hora_inicio = "00:00"

    if not hora_fin:
        hora_fin = "23:30"

    if hora_inicio > hora_fin:
        hora_inicio = "00:00"
        hora_fin = "23:30"

    ultimo_registro = None
    columnas_horas = generar_columnas_media_hora(hora_inicio, hora_fin)
    tabla_bateria = []
    datos_grafico_dia = []
    mensaje = ""
    horario_sugerido_aplicado = False
    datos_grafico_periodo = []
    
    clase_bateria_actual = "tarjeta-neutra"

    estado_descarga = "-"
    clase_descarga = "tarjeta-neutra"

    estado_estatus = "-"
    clase_estado = "tarjeta-neutra"

    texto_contiene_bateria = "Sin dato"
    clase_contiene_bateria = "chip-neutro"

    texto_error_bateria = "Sin dato"
    clase_error_bateria = "chip-neutro"

    total_caidas_drasticas = 0
    clase_alertas_periodo = "tarjeta-neutra"
    alertas_periodo = []
    
    if amid:
        fecha_inicio = timezone.now() - timedelta(days=dias)

        registros = EstadoValidadorLimpio.objects.filter(
            amid=amid,
            fecha_hora__gte=fecha_inicio
        ).order_by("fecha_hora")

        ultimo_registro = registros.order_by("-fecha_hora").first()

        if ultimo_registro:
            if usar_sugerido == "1":
                hora_inicio, hora_fin = calcular_rango_horario_sugerido(
                    registros=registros,
                    cantidad_dias=dias
                )
                horario_sugerido_aplicado = True

            columnas_horas, tabla_bateria = construir_tabla_bateria(
                registros=registros,
                cantidad_dias=dias,
                hora_inicio=hora_inicio,
                hora_fin=hora_fin
            )

            datos_grafico_periodo = construir_datos_grafico_periodo(tabla_bateria)
            datos_grafico_dia = construir_datos_grafico_dia(registros)
            clase_bateria_actual = obtener_clase_tarjeta_bateria(
                ultimo_registro.porcentaje_bateria
            )

            estado_descarga, clase_descarga = evaluar_fecha_descarga(
                ultimo_registro.fec_descarga
            )

            estado_estatus, clase_estado = evaluar_fecha_estatus(
                ultimo_registro.fec_estado
            )

            texto_contiene_bateria, clase_contiene_bateria = evaluar_chip_booleano(
                ultimo_registro.is_contiene_bateria
            )

            texto_error_bateria, clase_error_bateria = evaluar_error_bateria(
                ultimo_registro.is_error_obtener_bateria
            )

            alertas_periodo = detectar_caidas_drasticas_tabla(tabla_bateria)
            total_caidas_drasticas = len(alertas_periodo)

            if total_caidas_drasticas > 0:
                clase_alertas_periodo = "tarjeta-error"
            else:
                clase_alertas_periodo = "tarjeta-ok"
        else:
            mensaje = "No se encontraron registros para el AMID ingresado en el rango seleccionado."

    return {
        "amid": amid,
        "dias": dias,
        "hora_inicio": hora_inicio,
        "hora_fin": hora_fin,
        "ultimo_registro": ultimo_registro,
        "columnas_horas": columnas_horas,
        "tabla_bateria": tabla_bateria,
        "datos_grafico_dia": datos_grafico_dia,
        "mensaje": mensaje,
        "horario_sugerido_aplicado": horario_sugerido_aplicado,
        "datos_grafico_periodo": datos_grafico_periodo,
        "clase_bateria_actual": clase_bateria_actual,

        "estado_descarga": estado_descarga,
        "clase_descarga": clase_descarga,

        "estado_estatus": estado_estatus,
        "clase_estado": clase_estado,

        "texto_contiene_bateria": texto_contiene_bateria,
        "clase_contiene_bateria": clase_contiene_bateria,

        "texto_error_bateria": texto_error_bateria,
        "clase_error_bateria": clase_error_bateria,

        "total_caidas_drasticas": total_caidas_drasticas,
        "clase_alertas_periodo": clase_alertas_periodo,
        "alertas_periodo": alertas_periodo,
    }


def generar_columnas_media_hora(hora_inicio="00:00", hora_fin="23:30"):
    columnas = []
    inicio = datetime.strptime(hora_inicio, "%H:%M").time()
    fin = datetime.strptime(hora_fin, "%H:%M").time()

    for hora in range(24):
        for minuto in [0, 30]:
            hora_texto = f"{hora:02d}:{minuto:02d}"
            hora_obj = datetime.strptime(hora_texto, "%H:%M").time()

            if inicio <= hora_obj <= fin:
                columnas.append(hora_texto)

    return columnas


def generar_fechas_ultimos_dias(cantidad_dias=14):
    hoy = timezone.localdate()
    fechas = []

    for i in range(cantidad_dias):
        fechas.append(hoy - timedelta(days=i))

    return fechas


def obtener_registro_mas_cercano(registros_por_fecha, fecha, hora_texto, tolerancia_minutos=15):
    hora_obj = datetime.strptime(hora_texto, "%H:%M").time()
    fecha_hora_referencia = datetime.combine(fecha, hora_obj)

    if timezone.is_naive(fecha_hora_referencia):
        fecha_hora_referencia = timezone.make_aware(fecha_hora_referencia)

    registros_del_dia = registros_por_fecha.get(fecha, [])
    mejor_registro = None
    menor_diferencia = None

    for registro in registros_del_dia:
        if not registro.fecha_hora:
            continue

        diferencia = abs((registro.fecha_hora - fecha_hora_referencia).total_seconds()) / 60

        if diferencia <= tolerancia_minutos:
            if menor_diferencia is None or diferencia < menor_diferencia:
                menor_diferencia = diferencia
                mejor_registro = registro

    return mejor_registro


def construir_tabla_bateria(registros, cantidad_dias=14, hora_inicio="00:00", hora_fin="23:30"):
    columnas_horas = generar_columnas_media_hora(hora_inicio, hora_fin)
    fechas = generar_fechas_ultimos_dias(cantidad_dias)
    registros_por_fecha = {}

    for registro in registros:
        if not registro.fecha_hora:
            continue

        fecha = timezone.localtime(registro.fecha_hora).date()
        registros_por_fecha.setdefault(fecha, []).append(registro)

    tabla = []

    for fecha in fechas:
        fila = {
            "fecha": fecha.strftime("%d-%m-%Y"),
            "valores": []
        }

        for hora_texto in columnas_horas:
            registro_cercano = obtener_registro_mas_cercano(
                registros_por_fecha=registros_por_fecha,
                fecha=fecha,
                hora_texto=hora_texto,
                tolerancia_minutos=15
            )

            if registro_cercano and registro_cercano.porcentaje_bateria is not None:
                valor = registro_cercano.porcentaje_bateria
            else:
                valor = ""

            fila["valores"].append({
                "hora": hora_texto,
                "valor": valor,
                "clase": obtener_clase_bateria(valor),
            })

        tabla.append(fila)

    return columnas_horas, tabla


def obtener_clase_bateria(valor):
    if valor == "" or valor is None:
        return "bateria-sin-dato"

    try:
        valor = float(valor)
    except (ValueError, TypeError):
        return "bateria-sin-dato"

    if valor >= 80:
        return "bateria-alta"
    if valor >= 50:
        return "bateria-media"
    if valor >= 20:
        return "bateria-baja"
    return "bateria-critica"


def construir_datos_grafico_dia(registros, fecha_objetivo=None):
    if fecha_objetivo is None:
        fecha_objetivo = timezone.localdate()

    columnas_horas = generar_columnas_media_hora("00:00", "23:30")
    registros_por_fecha = {}

    for registro in registros:
        if not registro.fecha_hora:
            continue

        fecha = timezone.localtime(registro.fecha_hora).date()
        registros_por_fecha.setdefault(fecha, []).append(registro)

    datos = []
    for hora_texto in columnas_horas:
        registro_cercano = obtener_registro_mas_cercano(
            registros_por_fecha=registros_por_fecha,
            fecha=fecha_objetivo,
            hora_texto=hora_texto,
            tolerancia_minutos=15
        )

        bateria_real = None
        if registro_cercano and registro_cercano.porcentaje_bateria is not None:
            try:
                bateria_real = float(registro_cercano.porcentaje_bateria)
            except (ValueError, TypeError):
                bateria_real = None

        datos.append({
            "hora": hora_texto,
            "bateria_real": bateria_real,
            "bateria_esperada": None,
        })

    indices_validos = [i for i, punto in enumerate(datos)
                      if punto["bateria_real"] is not None and punto["bateria_real"] > 0]

    if not indices_validos:
        return []

    indice_inicio = indices_validos[0]
    indice_fin = indices_validos[-1]
    bateria_inicio = datos[indice_inicio]["bateria_real"]

    for indice in range(indice_inicio, indice_fin + 1):
        bloques_transcurridos = indice - indice_inicio
        datos[indice]["bateria_esperada"] = max(
            bateria_inicio - bloques_transcurridos * 3,
            0
        )

    return datos[indice_inicio:indice_fin + 1]


def construir_datos_grafico_periodo(tabla_bateria):
    datos = []

    tabla_ordenada = list(reversed(tabla_bateria))

    for fila in tabla_ordenada:
        fecha = fila["fecha"]

        for celda in fila["valores"]:
            valor = celda["valor"]

            if valor == "" or valor is None:
                bateria_real = None
            else:
                try:
                    bateria_real = float(valor)
                except (ValueError, TypeError):
                    bateria_real = None

            datos.append({
                "fecha": fecha,
                "hora": celda["hora"],
                "momento": f"{fecha} {celda['hora']}",
                "bateria_real": bateria_real,
            })

    return datos

def calcular_rango_horario_sugerido(registros, cantidad_dias=14):
    columnas_horas = generar_columnas_media_hora("00:00", "23:30")
    conteo_por_hora = {hora: 0 for hora in columnas_horas}

    for registro in registros:
        if not registro.fecha_hora:
            continue

        fecha_hora_local = timezone.localtime(registro.fecha_hora)
        hora = fecha_hora_local.hour
        minuto = fecha_hora_local.minute

        if minuto < 15:
            bloque = f"{hora:02d}:00"
        elif minuto < 45:
            bloque = f"{hora:02d}:30"
        else:
            hora_siguiente = hora + 1
            if hora_siguiente == 24:
                bloque = "23:30"
            else:
                bloque = f"{hora_siguiente:02d}:00"

        if bloque in conteo_por_hora:
            conteo_por_hora[bloque] += 1

    largo_ventana = 9
    mejor_inicio = 0
    mejor_total = -1

    for i in range(0, len(columnas_horas) - largo_ventana + 1):
        ventana = columnas_horas[i:i + largo_ventana]
        total = sum(conteo_por_hora[hora] for hora in ventana)

        if total > mejor_total:
            mejor_total = total
            mejor_inicio = i

    if mejor_total <= 0:
        return "00:00", "23:30"

    return columnas_horas[mejor_inicio], columnas_horas[mejor_inicio + largo_ventana - 1]

def detectar_caidas_drasticas_tabla(
    tabla_bateria,
    umbral_caida=30,
    ventana_horas=2,
    ventana_confirmacion_minutos=60
):
    """
    Detecta caídas drásticas usando la misma tabla visible del panel.

    Regla general:
    - Detecta caídas de al menos `umbral_caida` puntos dentro de `ventana_horas`.

    Regla especial para batería 0:
    - Si cae a 0 y luego vuelve rápido a un valor normal, se considera posible error de transmisión.
    - Si cae a 0 y se mantiene en 0, sigue baja, o no vuelve a transmitir dentro de la ventana de confirmación,
      se considera caída drástica.
    """

    puntos = []

    # La tabla viene desde hoy hacia atrás, por eso se invierte para analizar en orden cronológico.
    tabla_ordenada = list(reversed(tabla_bateria))

    for fila in tabla_ordenada:
        fecha_texto = fila["fecha"]

        try:
            fecha = datetime.strptime(fecha_texto, "%d-%m-%Y").date()
        except ValueError:
            continue

        for celda in fila["valores"]:
            valor = celda["valor"]

            if valor == "" or valor is None:
                continue

            try:
                bateria = float(valor)
            except (ValueError, TypeError):
                continue

            try:
                hora = datetime.strptime(celda["hora"], "%H:%M").time()
            except ValueError:
                continue

            fecha_hora = datetime.combine(fecha, hora)

            if timezone.is_naive(fecha_hora):
                fecha_hora = timezone.make_aware(fecha_hora)

            puntos.append({
                "fecha_hora": fecha_hora,
                "bateria": bateria,
            })

    puntos = sorted(puntos, key=lambda item: item["fecha_hora"])

    caidas = []
    ventana_maxima = timedelta(hours=ventana_horas)
    ventana_confirmacion = timedelta(minutes=ventana_confirmacion_minutos)

    for indice, actual in enumerate(puntos):
        if indice == 0:
            continue

        anterior = puntos[indice - 1]

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

        # Caso especial: caída a 0.
        if bateria_actual == 0:
            if es_cero_probablemente_transitorio(
                puntos=puntos,
                indice_actual=indice,
                bateria_anterior=bateria_anterior,
                umbral_caida=umbral_caida,
                ventana_confirmacion=ventana_confirmacion
            ):
                continue

        caidas.append({
            "fecha_hora": actual["fecha_hora"],
            "fecha_anterior": anterior["fecha_hora"],
            "bateria_anterior": bateria_anterior,
            "bateria_actual": bateria_actual,
            "caida": caida,
            "tiempo_transcurrido": formatear_duracion(tiempo_transcurrido),
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