from django.shortcuts import render
from urllib.parse import urlencode

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
    obtener_opciones_ubicacion_esperada,
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
from django.contrib.auth.decorators import login_required

import os
from io import BytesIO, StringIO
from django.conf import settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.shortcuts import redirect
from .models import EstadoValidadorLimpio, LogImportacion


def usuario_es_admin(user):
    return user.is_superuser or user.groups.filter(name="Admin").exists()


@login_required
def ejecutar_comando_admin(request):
    if not usuario_es_admin(request.user):
        messages.error(request, "No tienes permisos para ejecutar acciones administrativas.")
        return redirect("dashboard:panel_perfil")

    if request.method != "POST":
        return redirect("dashboard:panel_perfil")

    accion = request.POST.get("accion")
    salida = StringIO()

    try:
        if accion == "probar_oracle":
            call_command("probar_oracle", stdout=salida, stderr=salida)

        elif accion == "actualizar_validadores":
            call_command("actualizar_validadores", stdout=salida, stderr=salida)

        elif accion == "importar_oracle_2h":
            call_command("importar_validadores_oracle", stdout=salida, stderr=salida)

        elif accion == "importar_oracle_14d":
            call_command("importar_validadores_oracle", dias=14, stdout=salida, stderr=salida)

        elif accion == "cargar_limpios":
            call_command("cargar_validadores_limpios", stdout=salida, stderr=salida)

        elif accion == "limpiar_antiguos":
            call_command("limpiar_registros_antiguos", stdout=salida, stderr=salida)

        elif accion == "importar_ubicaciones":
            archivo = request.FILES.get("archivo_version_zp")

            if not archivo:
                messages.error(request, "Debes seleccionar un archivo Excel.")
                return redirect("dashboard:panel_perfil")

            carpeta_tmp = os.path.join(settings.BASE_DIR, "temp_uploads")
            os.makedirs(carpeta_tmp, exist_ok=True)

            storage = FileSystemStorage(location=carpeta_tmp)
            nombre_archivo = storage.save(archivo.name, archivo)
            ruta_archivo = storage.path(nombre_archivo)

            call_command(
                "importar_ubicaciones_esperadas",
                ruta_archivo,
                stdout=salida,
                stderr=salida,
            )

            try:
                os.remove(ruta_archivo)
            except OSError:
                pass

        else:
            messages.error(request, "Acción no reconocida.")
            return redirect("dashboard:panel_perfil")

        request.session["resultado_comando_admin"] = salida.getvalue()
        messages.success(request, "Proceso ejecutado correctamente.")

    except Exception as error:
        request.session["resultado_comando_admin"] = salida.getvalue()
        messages.error(request, f"Error ejecutando proceso: {error}")

    return redirect("dashboard:panel_perfil")

@login_required
def panel_alertas(request):
    dias = request.GET.get("dias", 1)
    tipo_alerta = request.GET.get("tipo", "gps_cero")
    mostrar_todo = request.GET.get("ver") == "todo"

    tipos_validos = ["gps_cero", "caidas_bateria", "fuera_radio"]

    if tipo_alerta not in tipos_validos:
        tipo_alerta = "gps_cero"

    contexto_gps_cero = obtener_alertas_gps_cero(
        dias=dias,
        mostrar_todo=mostrar_todo,
        ubicaciones_seleccionadas=None,
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
        ubicaciones_seleccionadas=None,
    )

    context = {
        **contexto_gps_cero,
        **contexto_caidas_bateria,
        **contexto_fuera_radio,
        "tipo_alerta": tipo_alerta,
    }

    return render(request, "dashboard/panel_alertas.html", context)

@login_required
def exportar_alertas_excel(request):
    dias = request.GET.get("dias", 1)

    contexto_gps_cero = obtener_alertas_gps_cero(
        dias=dias,
        mostrar_todo=True,
        ubicaciones_seleccionadas=None,
    )

    contexto_caidas_bateria = obtener_alertas_caidas_bateria(
        dias=dias,
        mostrar_todo=True,
        umbral_caida=30,
        ventana_horas=2,
    )

    contexto_fuera_radio = obtener_alertas_fuera_radio(
        dias=dias,
        mostrar_todo=True,
        ubicaciones_seleccionadas=None,
    )

    try:
        dias_int = int(dias)
    except ValueError:
        dias_int = 1

    wb = Workbook()

    # =========================
    # Hoja 1: GPS 0
    # =========================
    ws_gps = wb.active
    ws_gps.title = "GPS 0"

    ws_gps.append([
        "AMID",
        "Ubicación esperada",
        "Registros GPS 0",
        "Primera detección",
        "Última detección",
        "Última batería",
        "Frecuencia",
    ])

    for item in contexto_gps_cero["resumen_gps_cero"]:
        ws_gps.append([
            item.get("amid"),
            item.get("ubicacion_esperada"),
            item.get("cantidad_registros"),
            preparar_valor_excel(item.get("primera_deteccion")),
            preparar_valor_excel(item.get("ultima_deteccion")),
            item.get("ultima_bateria"),
            item.get("estado_alerta"),
        ])

    aplicar_estilo_hoja(ws_gps)

    # =========================
    # Hoja 2: Caídas batería
    # =========================
    ws_caidas = wb.create_sheet("Caidas bateria")

    ws_caidas.append([
        "AMID",
        "Caídas detectadas",
        "Mayor caída",
        "Última caída",
        "Batería anterior",
        "Batería actual",
        "Tiempo transcurrido",
    ])

    for item in contexto_caidas_bateria["resumen_caidas_bateria"]:
        ws_caidas.append([
            item.get("amid"),
            item.get("cantidad_caidas"),
            item.get("mayor_caida"),
            preparar_valor_excel(item.get("ultima_caida")),
            item.get("bateria_anterior"),
            item.get("bateria_actual"),
            item.get("tiempo_transcurrido"),
        ])

    aplicar_estilo_hoja(ws_caidas)

    # =========================
    # Hoja 3: Fuera de radio
    # =========================
    ws_fuera = wb.create_sheet("Fuera de radio")

    ws_fuera.append([
        "AMID",
        "Registros fuera",
        "Última detección",
        "Ubicación esperada",
        "Distancia metros",
        "Radio metros",
        "Exceso metros",
        "Mayor distancia",
        "Última batería",
    ])

    for item in contexto_fuera_radio["resumen_fuera_radio"]:
        ws_fuera.append([
            item.get("amid"),
            item.get("cantidad_registros"),
            preparar_valor_excel(item.get("ultima_deteccion")),
            item.get("nombre_ubicacion"),
            item.get("distancia_metros"),
            item.get("radio_metros"),
            item.get("exceso_metros"),
            item.get("mayor_distancia"),
            item.get("ultima_bateria"),
        ])

    aplicar_estilo_hoja(ws_fuera)

    output = BytesIO()
    wb.save(output)
    wb.close()
    output.seek(0)

    fecha_exportacion = timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M%S")
    filename = f"alertas_{dias_int}_dias_{fecha_exportacion}.xlsx"

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response

@login_required
def panel_baterias(request):
    contexto = obtener_contexto_baterias(request)
    contexto["active_page"] = "baterias"
    return render(request, "dashboard/panel_baterias.html", contexto)

@login_required
def panel_gps(request):
    contexto = obtener_contexto_gps(request)
    contexto["active_page"] = "gps"
    return render(request, "dashboard/panel_gps.html", contexto)

@login_required
def exportar_gps_excel(request):
    amid = request.GET.get("amid", "").strip()
    dias = request.GET.get("dias", "1")

    if not amid:
        return HttpResponse("Debe indicar un AMID para exportar.", status=400)

    try:
        dias = int(dias)
    except ValueError:
        dias = 1

    if dias not in [1, 3, 7, 14]:
        dias = 1

    fecha_inicio = timezone.now() - timedelta(days=dias)

    registros = (
        EstadoValidadorLimpio.objects
        .filter(
            amid=amid,
            fecha_hora__gte=fecha_inicio,
        )
        .only(
            "amid",
            "fecha_hora",
            "fec_descarga",
            "fec_estado",
            "latitud",
            "longitud",
            "porcentaje_bateria",
            "is_contiene_gps",
            "is_error_obtener_gps",
        )
        .order_by("fecha_hora")
    )

    if not registros.exists():
        return HttpResponse(
            f"No existen registros GPS para el AMID {amid} en el rango seleccionado.",
            status=404
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "GPS AMID"

    ws.append([
        "AMID",
        "Fecha hora",
        "Fecha descarga",
        "Fecha estado",
        "Latitud",
        "Longitud",
        "Porcentaje batería",
        "Contiene GPS",
        "Error GPS",
    ])

    for registro in registros.iterator(chunk_size=2000):
        ws.append([
            preparar_valor_excel(registro.amid),
            preparar_valor_excel(registro.fecha_hora),
            preparar_valor_excel(registro.fec_descarga),
            preparar_valor_excel(registro.fec_estado),
            preparar_valor_excel(registro.latitud),
            preparar_valor_excel(registro.longitud),
            preparar_valor_excel(registro.porcentaje_bateria),
            preparar_valor_excel(registro.is_contiene_gps),
            preparar_valor_excel(registro.is_error_obtener_gps),
        ])

    aplicar_estilo_hoja(ws)

    output = BytesIO()
    wb.save(output)
    wb.close()
    output.seek(0)

    filename = f"gps_amid_{amid}_{dias}_dias.xlsx"

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response

@login_required
def panel_perfil(request):
    usuario_actual = request.user

    es_admin = (
        usuario_actual.is_superuser
        or usuario_actual.groups.filter(name="Admin").exists()
    )

    roles_usuario_actual = usuario_actual.groups.values_list("name", flat=True)
    roles_usuario_actual = ", ".join(roles_usuario_actual)

    context = {
        "active_page": "perfil",
        "es_admin": es_admin,
        "usuario_actual": usuario_actual,
        "roles_usuario_actual": roles_usuario_actual or "Sin rol asignado",
    }

    if es_admin:
        usuarios = User.objects.all().order_by("username")

        total_usuarios = usuarios.count()
        usuarios_activos = usuarios.filter(is_active=True).count()
        usuarios_inactivos = usuarios.filter(is_active=False).count()
        total_admins = usuarios.filter(is_superuser=True).count()
        ultimos_logs = LogImportacion.objects.all().order_by("-fecha_inicio")[:8]
        resultado_comando_admin = request.session.pop("resultado_comando_admin", None)
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

        context.update({
            "total_usuarios": total_usuarios,
            "usuarios_activos": usuarios_activos,
            "usuarios_inactivos": usuarios_inactivos,
            "total_admins": total_admins,
            "resumen_roles": resumen_roles,
            "lista_usuarios": lista_usuarios,
            "ultimos_logs": ultimos_logs,
            "resultado_comando_admin": resultado_comando_admin,
        })

    return render(request, "dashboard/panel_perfil.html", context)

@login_required
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