from datetime import datetime, timedelta, time

from django.shortcuts import render
from django.utils import timezone

from .models import EstadoValidadorLimpio


def generar_columnas_media_hora(hora_inicio="00:00", hora_fin="23:30"):
    """
    Genera columnas de media hora filtradas por rango horario.
    Ejemplo:
    hora_inicio = "18:00"
    hora_fin = "22:00"
    """

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
    """
    Genera una lista de fechas desde hoy hacia atrás.
    """

    hoy = timezone.localdate()
    fechas = []

    for i in range(cantidad_dias):
        fechas.append(hoy - timedelta(days=i))

    return fechas


def obtener_registro_mas_cercano(registros_por_fecha, fecha, hora_texto, tolerancia_minutos=15):
    """
    Busca el registro más cercano a una hora de referencia,
    usando una tolerancia máxima de ±15 minutos.
    """

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
    """
    Construye la tabla:
    filas = últimos N días
    columnas = medias horas filtradas por rango horario
    celdas = porcentaje_bateria más cercano a cada bloque horario.
    """

    columnas_horas = generar_columnas_media_hora(hora_inicio, hora_fin)
    fechas = generar_fechas_ultimos_dias(cantidad_dias)

    registros_por_fecha = {}

    for registro in registros:
        if not registro.fecha_hora:
            continue

        fecha = timezone.localtime(registro.fecha_hora).date()

        if fecha not in registros_por_fecha:
            registros_por_fecha[fecha] = []

        registros_por_fecha[fecha].append(registro)

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

def obtener_sugerencias_horarios(tabla_bateria, columnas_horas):
    """
    Calcula qué horarios tienen más datos disponibles.
    Devuelve una lista de horarios sugeridos.
    """

    conteo_por_hora = {}

    for hora in columnas_horas:
        conteo_por_hora[hora] = 0

    for fila in tabla_bateria:
        for celda in fila["valores"]:
            if celda["valor"] != "" and celda["valor"] is not None:
                conteo_por_hora[celda["hora"]] += 1

    horarios_ordenados = sorted(
        conteo_por_hora.items(),
        key=lambda item: item[1],
        reverse=True
    )

    sugerencias = []

    for hora, cantidad in horarios_ordenados[:6]:
        if cantidad > 0:
            sugerencias.append({
                "hora": hora,
                "cantidad": cantidad
            })

    return sugerencias

def calcular_rango_horario_sugerido(registros, cantidad_dias=14):
    """
    Calcula un rango horario sugerido según la mayor concentración de datos.
    Revisa los bloques de media hora y busca una ventana de 4 horas con más registros.
    """

    columnas_horas = generar_columnas_media_hora("00:00", "23:30")

    conteo_por_hora = {hora: 0 for hora in columnas_horas}

    for registro in registros:
        if not registro.fecha_hora:
            continue

        fecha_hora_local = timezone.localtime(registro.fecha_hora)
        hora = fecha_hora_local.hour
        minuto = fecha_hora_local.minute

        # Redondeamos al bloque de media hora más cercano
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

    # Ventana sugerida de 4 horas = 9 puntos:
    # 18:00, 18:30, 19:00, ..., 22:00
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

    hora_inicio = columnas_horas[mejor_inicio]
    hora_fin = columnas_horas[mejor_inicio + largo_ventana - 1]

    return hora_inicio, hora_fin

def obtener_clase_bateria(valor):
    """
    Devuelve una clase CSS según el nivel de batería.
    """

    if valor == "" or valor is None:
        return "bateria-sin-dato"

    try:
        valor = float(valor)
    except ValueError:
        return "bateria-sin-dato"

    if valor >= 80:
        return "bateria-alta"
    elif valor >= 50:
        return "bateria-media"
    elif valor >= 20:
        return "bateria-baja"
    else:
        return "bateria-critica"

def construir_datos_grafico_dia(registros, fecha_objetivo=None):
    """
    Prepara datos para el gráfico del día actual.
    Todavía no dibuja el gráfico, solo arma la data.
    """

    if fecha_objetivo is None:
        fecha_objetivo = timezone.localdate()

    columnas_horas = generar_columnas_media_hora()

    registros_por_fecha = {}

    for registro in registros:
        if not registro.fecha_hora:
            continue

        fecha = timezone.localtime(registro.fecha_hora).date()

        if fecha not in registros_por_fecha:
            registros_por_fecha[fecha] = []

        registros_por_fecha[fecha].append(registro)

    datos = []

    for indice, hora_texto in enumerate(columnas_horas):
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
            except ValueError:
                bateria_real = None

        bateria_esperada = max(100 - indice * 4, 0)

        datos.append({
            "hora": hora_texto,
            "bateria_real": bateria_real,
            "bateria_esperada": bateria_esperada,
        })

    return datos

def panel_baterias(request):
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

    context = {
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
        "datos_grafico_dia": datos_grafico_dia,

    }

    return render(request, "dashboard/panel_baterias.html", context)

def construir_datos_grafico_periodo(tabla_bateria):
    """
    Construye datos para graficar la evolución de batería
    en el período seleccionado.
    Usa la misma tabla ya calculada, por lo tanto respeta filtros de días y horas.
    """

    datos = []

    # La tabla viene desde hoy hacia atrás.
    # Para el gráfico conviene mostrar desde el día más antiguo al más reciente.
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
                except ValueError:
                    bateria_real = None

            datos.append({
                "momento": f"{fecha} {celda['hora']}",
                "bateria_real": bateria_real,
            })

    return datos