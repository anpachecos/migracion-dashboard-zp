from datetime import datetime, timedelta

from django.utils import timezone

from ..models import EstadoValidadorLimpio


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
    datos_por_dia = {}
    tabla_ordenada = list(reversed(tabla_bateria))

    for fila in tabla_ordenada:
        fecha = fila["fecha"]
        valores_del_dia = []

        for celda in fila["valores"]:
            valor = celda["valor"]
            if valor != "" and valor is not None:
                try:
                    valores_del_dia.append(float(valor))
                except (ValueError, TypeError):
                    pass

        if valores_del_dia:
            datos_por_dia[fecha] = sum(valores_del_dia) / len(valores_del_dia)
        else:
            datos_por_dia[fecha] = None

    datos = []
    for fecha, bateria_promedio in datos_por_dia.items():
        datos.append({
            "fecha": fecha,
            "bateria_real": bateria_promedio,
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
