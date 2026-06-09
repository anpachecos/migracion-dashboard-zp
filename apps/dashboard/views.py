from django.shortcuts import render

from .services.baterias_service import (
    obtener_contexto_baterias,
    generar_columnas_media_hora,
    construir_tabla_bateria,
)
from .services.gps_service import obtener_contexto_gps
from .services.alertas_service import (
    obtener_alertas_gps_cero,
    obtener_alertas_caidas_bateria,
    obtener_alertas_fuera_radio,
)
from django.contrib.auth.models import User, Group

#Para exportar excel
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from django.utils import timezone
from .models import EstadoValidadorLimpio

from io import BytesIO

from datetime import datetime, timedelta
from django.utils import timezone


def panel_alertas(request):
    dias = request.GET.get("dias", 1)
    tipo_alerta = request.GET.get("tipo", "gps_cero")
    mostrar_todo = request.GET.get("ver") == "todo"

    tipos_validos = ["gps_cero", "caidas_bateria", "fuera_radio"]

    if tipo_alerta not in tipos_validos:
        tipo_alerta = "gps_cero"

    contexto_gps_cero = obtener_alertas_gps_cero(
        dias=dias,
        mostrar_todo=mostrar_todo
    )

    contexto_caidas_bateria = obtener_alertas_caidas_bateria(
        dias=dias,
        mostrar_todo=mostrar_todo,
        umbral_caida=30,
        ventana_horas=2,
    )
    
    contexto_fuera_radio = obtener_alertas_fuera_radio(
        dias=dias,
        mostrar_todo=mostrar_todo,
    )

    context = {
        **contexto_gps_cero,
        **contexto_caidas_bateria,
        **contexto_fuera_radio,
        "tipo_alerta": tipo_alerta,
    }

    return render(request, "dashboard/panel_alertas.html", context)

def panel_baterias(request):
    contexto = obtener_contexto_baterias(request)
    contexto["active_page"] = "baterias"
    return render(request, "dashboard/panel_baterias.html", contexto)

def panel_gps(request):
    contexto = obtener_contexto_gps(request)
    contexto["active_page"] = "gps"
    return render(request, "dashboard/panel_gps.html", contexto)

def panel_perfil(request):
    usuarios = User.objects.all().order_by("username")

    total_usuarios = usuarios.count()
    usuarios_activos = usuarios.filter(is_active=True).count()
    usuarios_inactivos = usuarios.filter(is_active=False).count()
    total_admins = usuarios.filter(is_superuser=True).count()

    grupos = Group.objects.all().order_by("name")

    resumen_roles = []

    for grupo in grupos:
        resumen_roles.append({
            "nombre": grupo.name,
            "cantidad": grupo.user_set.count(),
        })

    lista_usuarios = []

    for usuario in usuarios:
        grupos_usuario = usuario.groups.all()
        roles = ", ".join([grupo.name for grupo in grupos_usuario])

        if usuario.is_superuser:
            roles = "Admin" if not roles else f"Admin, {roles}"

        lista_usuarios.append({
            "username": usuario.username,
            "email": usuario.email,
            "nombre": usuario.get_full_name() or "-",
            "roles": roles or "Sin rol",
            "activo": usuario.is_active,
            "ultimo_acceso": usuario.last_login,
            "fecha_creacion": usuario.date_joined,
            "es_admin": usuario.is_superuser,
        })

    return render(request, "dashboard/panel_perfil.html", {
        "active_page": "perfil",
        "total_usuarios": total_usuarios,
        "usuarios_activos": usuarios_activos,
        "usuarios_inactivos": usuarios_inactivos,
        "total_admins": total_admins,
        "resumen_roles": resumen_roles,
        "lista_usuarios": lista_usuarios,
    })

def exportar_baterias_excel(request):
    """
    Exporta a Excel los datos del AMID consultado.
    Hoja 1: matriz fecha x hora, igual a la tabla del panel.
    Hoja 2: registros completos del AMID.
    """

    amid = request.GET.get("amid", "").strip()
    dias = request.GET.get("dias", "14")
    hora_inicio = request.GET.get("hora_inicio", "00:00")
    hora_fin = request.GET.get("hora_fin", "23:30")

    if not amid:
        response = HttpResponse("Debe indicar un AMID para exportar.", status=400)
        return response

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

    fecha_inicio = timezone.now() - timedelta(days=dias)

    registros = EstadoValidadorLimpio.objects.filter(
        amid=amid,
        fecha_hora__gte=fecha_inicio
    ).order_by("fecha_hora")

    if not registros.exists():
        return HttpResponse(
            f"No existen registros para el AMID {amid} en el rango seleccionado.",
            status=404
        )

    columnas_horas, tabla_bateria = construir_tabla_bateria(
        registros=registros,
        cantidad_dias=dias,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin
    )

    wb = Workbook()

    # =========================
    # Hoja 1: tabla batería
    # =========================
    ws_tabla = wb.active
    ws_tabla.title = "Tabla bateria"

    ws_tabla.append(["AMID", amid])
    ws_tabla.append(["Periodo", f"Últimos {dias} día(s)"])
    ws_tabla.append(["Horario", f"{hora_inicio} a {hora_fin}"])
    ws_tabla.append([])

    encabezados_tabla = ["Fecha"] + columnas_horas
    ws_tabla.append(encabezados_tabla)

    for fila in tabla_bateria:
        valores = [fila["fecha"]]

        for celda in fila["valores"]:
            valores.append(celda["valor"] if celda["valor"] != "" else None)

        ws_tabla.append(valores)

    aplicar_estilo_tabla_bateria(ws_tabla)

    # =========================
    # Hoja 2: registros del AMID
    # =========================
    ws_datos = wb.create_sheet("Registros AMID")

    encabezados_datos = [
        "AMID",
        "Fecha hora",
        "Fecha descarga",
        "Fecha estado",
        "BUSID",
        "OP",
        "Patente",
        "Porcentaje batería",
        "Tiempo vida",
        "Batería detectada",
        "Error batería",
        "Latitud",
        "Longitud",
    ]

    ws_datos.append(encabezados_datos)

    for registro in registros.iterator(chunk_size=2000):
        ws_datos.append([
            preparar_valor_excel(registro.amid),
            preparar_valor_excel(registro.fecha_hora),
            preparar_valor_excel(registro.fec_descarga),
            preparar_valor_excel(registro.fec_estado),
            preparar_valor_excel(registro.busid),
            preparar_valor_excel(registro.op),
            preparar_valor_excel(registro.patente),
            preparar_valor_excel(registro.porcentaje_bateria),
            preparar_valor_excel(registro.tiempo_vida),
            preparar_valor_excel(registro.is_contiene_bateria),
            preparar_valor_excel(registro.is_error_obtener_bateria),
            preparar_valor_excel(registro.latitud),
            preparar_valor_excel(registro.longitud),
        ])

    aplicar_estilo_hoja(ws_datos)

    output = BytesIO()
    wb.save(output)
    wb.close()
    output.seek(0)

    filename = f"bateria_amid_{amid}.xlsx"

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response

def preparar_fecha_excel(valor):
    """
    Convierte fechas con zona horaria a fechas compatibles con Excel.
    Excel no acepta datetimes con tzinfo.
    """

    if not valor:
        return None

    if timezone.is_aware(valor):
        valor = timezone.localtime(valor)
        valor = valor.replace(tzinfo=None)

    return valor

def aplicar_estilo_hoja(ws):
    """
    Aplica formato básico a una hoja Excel.
    """

    fill_header = PatternFill(
        start_color="1F4E78",
        end_color="1F4E78",
        fill_type="solid"
    )

    font_header = Font(
        color="FFFFFF",
        bold=True
    )

    border = Border(
        left=Side(style="thin", color="D9E2F3"),
        right=Side(style="thin", color="D9E2F3"),
        top=Side(style="thin", color="D9E2F3"),
        bottom=Side(style="thin", color="D9E2F3"),
    )

    for cell in ws[1]:
        cell.fill = fill_header
        cell.font = font_header
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for row in ws.iter_rows():
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="center")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    for column_cells in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column_cells[0].column)

        for cell in column_cells:
            if cell.value is not None:
                max_length = max(max_length, len(str(cell.value)))

        adjusted_width = min(max_length + 2, 35)
        ws.column_dimensions[column_letter].width = adjusted_width
        
def preparar_valor_excel(valor):
    """
    Prepara valores para Excel.
    Si es datetime con zona horaria, lo convierte a hora local
    y elimina tzinfo, porque Excel no soporta timezone.
    """

    if valor is None:
        return None

    if isinstance(valor, datetime):
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)

        return valor.replace(tzinfo=None)

    return valor

def aplicar_estilo_tabla_bateria(ws):
    """
    Aplica estilo a la hoja con la matriz fecha x hora.
    """

    fill_titulo = PatternFill("solid", fgColor="1F4E78")
    fill_header = PatternFill("solid", fgColor="D9EAF7")
    font_titulo = Font(color="FFFFFF", bold=True)
    font_header = Font(bold=True, color="1F1F1F")

    border = Border(
        left=Side(style="thin", color="D9E2F3"),
        right=Side(style="thin", color="D9E2F3"),
        top=Side(style="thin", color="D9E2F3"),
        bottom=Side(style="thin", color="D9E2F3"),
    )

    # Estilo de las primeras filas informativas
    for row in range(1, 4):
        ws[f"A{row}"].fill = fill_titulo
        ws[f"A{row}"].font = font_titulo
        ws[f"A{row}"].alignment = Alignment(horizontal="center")

    # Encabezados están en la fila 5
    fila_header = 5

    for cell in ws[fila_header]:
        cell.fill = fill_header
        cell.font = font_header
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    # Bordes + alineación para toda la tabla
    for row in ws.iter_rows(min_row=fila_header, max_row=ws.max_row):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center")

    # Colores de batería en celdas numéricas
    for row in ws.iter_rows(min_row=fila_header + 1, max_row=ws.max_row, min_col=2, max_col=ws.max_column):
        for cell in row:
            valor = cell.value

            if valor is None:
                cell.fill = PatternFill("solid", fgColor="F1F3F5")
                continue

            try:
                bateria = float(valor)
            except (ValueError, TypeError):
                continue

            if bateria >= 80:
                cell.fill = PatternFill("solid", fgColor="D1E7DD")
            elif bateria >= 50:
                cell.fill = PatternFill("solid", fgColor="FFF3CD")
            elif bateria >= 20:
                cell.fill = PatternFill("solid", fgColor="FFE5D0")
            else:
                cell.fill = PatternFill("solid", fgColor="F8D7DA")

    ws.freeze_panes = "B6"
    ws.auto_filter.ref = f"A5:{get_column_letter(ws.max_column)}{ws.max_row}"

    ws.column_dimensions["A"].width = 14

    for col in range(2, ws.max_column + 1):
        letra = get_column_letter(col)
        ws.column_dimensions[letra].width = 8