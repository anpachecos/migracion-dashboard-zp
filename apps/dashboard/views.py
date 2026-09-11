import os
from io import StringIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.dashboard.services.alertas_service import (
    LIMITE_SUGERENCIAS_ALERTAS,
    MIN_CARACTERES_BUSQUEDA_ALERTAS,
    buscar_amids_alertas,
    buscar_ubicaciones_alertas,
    obtener_contexto_alertas,
    obtener_ubicaciones_alertas_disponibles,
    obtener_alertas_para_exportar,
)
from apps.dashboard.services.oracle_connection import obtener_conexion_oracle
from apps.dashboard.services.exportaciones_service import (
    COLUMNAS_EXCEL_ALERTAS,
    crear_excel_alertas,
    crear_excel_completo_amid as construir_excel_completo_amid,
    serializar_excel,
)
from apps.dashboard.services.preferencias_alertas_service import (
    guardar_preferencias_alertas_usuario,
    obtener_preferencias_alertas_usuario,
)
from apps.dashboard.services.reglas_alertas_service import (
    actualizar_reglas_alertas,
    iniciar_recalculo_en_segundo_plano,
    leer_log_recalculo,
    obtener_editor_reglas_alertas,
    recalculo_en_curso,
    usuario_puede_editar_reglas,
)
from apps.dashboard.services.ubicaciones_service import (
    sincronizar_amids_ubicaciones_oracle,
)

from .models import LogImportacion
from .services.baterias_service import (
    construir_tabla_bateria,
    obtener_ahora_referencia,
    obtener_bloques_bateria_oracle,
    obtener_contexto_baterias,
    obtener_detalle_caidas_bateria_oracle,
    obtener_rango_fechas_panel,
)
from .services.gps_service import obtener_contexto_gps

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

    acciones_antiguas_sqlite = [
        "actualizar_validadores",
        "importar_oracle_2h",
        "importar_oracle_14d",
        "cargar_limpios",
        "limpiar_antiguos",
    ]

    try:
        if accion == "probar_oracle":
            call_command("probar_oracle", stdout=salida, stderr=salida)

        elif accion == "sincronizar_amids_ubicaciones":
            resultado = sincronizar_amids_ubicaciones_oracle()
            salida.write(
                "Sincronización Oracle finalizada.\n"
                f"Ubicaciones creadas: {resultado['ubicaciones_creadas']}\n"
                f"Historiales abiertos: {resultado['historiales_creados']}\n"
                f"AMID activos sin ubicación: {resultado['sin_ubicacion']}\n"
                "AMID activos sin historial abierto: "
                f"{resultado['sin_historial_abierto']}"
            )

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

            try:
                call_command(
                    "importar_ubicaciones_esperadas",
                    ruta_archivo,
                    stdout=salida,
                    stderr=salida,
                )
            finally:
                try:
                    os.remove(ruta_archivo)
                except OSError:
                    pass

        elif accion in acciones_antiguas_sqlite:
            messages.warning(
                request,
                "Esta acción pertenece al flujo antiguo SQLite y está deshabilitada. "
                "Los datos operativos ahora se consultan directamente desde Oracle."
            )
            return redirect("dashboard:panel_perfil")

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
def buscar_exclusiones_alertas(request):
    """Endpoint liviano para los autocompletados del panel de alertas."""

    if request.method != "GET":
        return JsonResponse({"detalle": "Metodo no permitido."}, status=405)

    tipo = request.GET.get("tipo", "").strip().lower()
    termino = request.GET.get("q", "").strip()[:120]

    if len(termino) < MIN_CARACTERES_BUSQUEDA_ALERTAS:
        return JsonResponse(
            {
                "resultados": [],
                "minimo_caracteres": MIN_CARACTERES_BUSQUEDA_ALERTAS,
            }
        )

    if tipo == "amid":
        valores = buscar_amids_alertas(termino, LIMITE_SUGERENCIAS_ALERTAS)
    elif tipo == "ubicacion":
        valores = buscar_ubicaciones_alertas(termino, LIMITE_SUGERENCIAS_ALERTAS)
    else:
        return JsonResponse({"detalle": "Tipo de busqueda no valido."}, status=400)

    return JsonResponse(
        {
            "resultados": [
                {
                    "valor": valor,
                    "etiqueta": valor,
                }
                for valor in valores
            ],
            "minimo_caracteres": MIN_CARACTERES_BUSQUEDA_ALERTAS,
            "limite": LIMITE_SUGERENCIAS_ALERTAS,
        }
    )


@login_required
def detalle_caidas_bateria(request):
    """Devuelve las caídas de un AMID solo cuando el usuario abre el detalle."""
    if request.method != "GET":
        return JsonResponse({"detalle": "Metodo no permitido."}, status=405)

    amid = request.GET.get("amid", "").strip()
    if not amid or not amid.isdigit():
        return JsonResponse(
            {"detalle": "Debes indicar un AMID valido."},
            status=400,
        )

    try:
        resultado = obtener_detalle_caidas_bateria_oracle(amid=amid, dias=14)
    except Exception:
        return JsonResponse(
            {"detalle": "El detalle de caidas de Oracle no esta disponible."},
            status=503,
        )

    return JsonResponse(resultado)


@login_required
def panel_alertas(request):
    if request.method == "POST":
        # Se obtiene el catalogo completo solo al guardar para conservar la
        # validacion existente. En los GET ya no se envia al HTML.
        ubicaciones_disponibles = obtener_ubicaciones_alertas_disponibles()
        limpiar_preferencias = request.POST.get("limpiar_preferencias") == "1"
        texto_amids = (
            ""
            if limpiar_preferencias
            else request.POST.get("amids_excluidos", "")
        )
        ubicaciones = (
            []
            if limpiar_preferencias
            else request.POST.getlist("ubicaciones_excluidas")
        )

        try:
            preferencias = guardar_preferencias_alertas_usuario(
                usuario=request.user,
                texto_amids=texto_amids,
                ubicaciones=ubicaciones,
                ubicaciones_disponibles=ubicaciones_disponibles,
            )
            if limpiar_preferencias:
                messages.success(request, "Preferencias de alertas restablecidas.")
            else:
                messages.success(
                    request,
                    "Preferencias guardadas: "
                    f"{len(preferencias['amids_excluidos'])} AMID y "
                    f"{len(preferencias['ubicaciones_excluidas'])} ubicaciones excluidas.",
                )
        except ValueError as error:
            messages.error(request, str(error))

        return redirect("dashboard:panel_alertas")

    preferencias = obtener_preferencias_alertas_usuario(request.user)

    try:
        contexto = obtener_contexto_alertas(request, preferencias=preferencias)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("dashboard:panel_alertas")

    contexto.update(
        {
            "preferencias_alertas": preferencias,
            "amids_excluidos_texto": ",".join(
                str(amid) for amid in preferencias["amids_excluidos"]
            ),
            "total_amids_excluidos": len(preferencias["amids_excluidos"]),
            "total_ubicaciones_excluidas": len(
                preferencias["ubicaciones_excluidas"]
            ),
            "total_preferencias_alertas": (
                len(preferencias["amids_excluidos"])
                + len(preferencias["ubicaciones_excluidas"])
            ),
        }
    )
    return render(request, "dashboard/panel_alertas.html", contexto)


@login_required
def exportar_alertas_excel(request):
    """Exporta todos los AMID activos, sin filtros ni preferencias de usuario."""

    alertas = obtener_alertas_para_exportar()
    fecha_generacion = obtener_ahora_referencia()
    wb = crear_excel_alertas(alertas, fecha_generacion=fecha_generacion)
    contenido_excel = serializar_excel(wb)

    nombre_archivo = (
        "panel_alertas_"
        f"{fecha_generacion.strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    response = HttpResponse(
        contenido_excel,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{nombre_archivo}"'
    )
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
    """
    Exporta el Excel estándar del AMID desde el botón GPS.

    Por ahora, igual que Baterías:
    - siempre exporta 14 días completos
    - no usa filtros de fecha/hora del panel GPS
    """

    amid = request.GET.get("amid", "").strip()

    if not amid:
        return HttpResponse("Debe indicar un AMID para exportar.", status=400)

    dias = 14
    hora_inicio = "00:00"
    hora_fin = "23:30"

    try:
        wb = crear_excel_completo_amid(
            amid=amid,
            dias=dias,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
        )
    except ValueError:
        return HttpResponse("El AMID ingresado no es válido.", status=400)
    except Exception as error:
        return HttpResponse(
            f"Error consultando datos en Oracle: {error}",
            status=500,
        )

    if wb is None:
        return HttpResponse(
            f"No existen registros para el AMID {amid} en los últimos 14 días.",
            status=404,
        )

    contenido_excel = serializar_excel(wb, cerrar=True)

    fecha_exportacion = obtener_ahora_referencia().strftime("%Y%m%d_%H%M%S")
    filename = f"datos_amid_{amid}_14_dias_{fecha_exportacion}.xlsx"

    response = HttpResponse(
        contenido_excel,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response
def obtener_registros_completos_oracle(amid, fecha_inicio, fecha_fin):
    """
    Obtiene todos los datos relevantes del AMID desde Oracle
    para la hoja 'Registros completos'.
    """

    fecha_inicio_texto = fecha_inicio.strftime("%Y-%m-%d %H:%M:%S")
    fecha_fin_texto = fecha_fin.strftime("%Y-%m-%d %H:%M:%S")

    query = """
        SELECT
            ID,
            AMID,
            FEC_DESCARGA,
            FEC_ESTADO,
            BUSID,
            OP,
            VERSION,
            PATENTE,
            TD01,
            TD04,
            TABLA,
            VER_TABLA,
            FECHA_HORA,
            IS_CONTIENE_BATERIA,
            IS_CONTIENE_GPS,
            IS_CONTIENE_TIEMPO_VIDA,
            IS_ERROR_OBTENER_BATERIA,
            IS_ERROR_OBTENER_GPS,
            IS_ERROR_OBTENER_TIEMPO_VIDA,
            LATITUD,
            LONGITUD,
            PORCENTAJE_BATERIA,
            TIEMPO_VIDA,
            FECHA_REGISTRO
        FROM USR_LAB.VW_ESTATUS_ZP_DJANGO
        WHERE AMID = :amid
          AND FECHA_HORA >= TO_DATE(:fecha_inicio, 'YYYY-MM-DD HH24:MI:SS')
          AND FECHA_HORA < TO_DATE(:fecha_fin, 'YYYY-MM-DD HH24:MI:SS')
        ORDER BY FECHA_HORA
    """

    registros = []

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "amid": int(amid),
                    "fecha_inicio": fecha_inicio_texto,
                    "fecha_fin": fecha_fin_texto,
                },
            )

            columnas = [col[0].lower() for col in cursor.description]

            for fila in cursor.fetchall():
                datos = dict(zip(columnas, fila))
                registros.append(datos)

    return registros


def crear_excel_completo_amid(amid, dias=14, hora_inicio="00:00", hora_fin="23:30"):
    """Obtiene los datos y delega la construcción del workbook estándar."""

    if not hora_inicio:
        hora_inicio = "00:00"

    if not hora_fin:
        hora_fin = "23:30"

    if hora_inicio > hora_fin:
        hora_inicio = "00:00"
        hora_fin = "23:30"

    dias = 14

    fecha_inicio, fecha_fin = obtener_rango_fechas_panel(dias)

    registros_dict = obtener_registros_completos_oracle(
        amid=amid,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )

    if not registros_dict:
        return None

    bloques_bateria = obtener_bloques_bateria_oracle(
        amid=amid,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )

    columnas_horas, tabla_bateria = construir_tabla_bateria(
        bloques=bloques_bateria,
        cantidad_dias=dias,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
    )

    return construir_excel_completo_amid(
        amid=amid,
        registros_dict=registros_dict,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        columnas_horas=columnas_horas,
        tabla_bateria=tabla_bateria,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        fecha_generacion=obtener_ahora_referencia(),
    )

@login_required
def panel_perfil(request):
    usuario_actual = request.user

    es_admin = usuario_es_admin(usuario_actual)

    roles_usuario_actual = usuario_actual.groups.values_list("name", flat=True)
    roles_usuario_actual = ", ".join(roles_usuario_actual)

    context = {
        "active_page": "perfil",
        "es_admin": es_admin,
        "usuario_actual": usuario_actual,
        "roles_usuario_actual": roles_usuario_actual or "Sin rol asignado",
        "abrir_editor_reglas": request.GET.get("editor_reglas") == "1",
    }

    if request.method == "POST" and es_admin:
        accion = request.POST.get("action")

        if accion in {"guardar_reglas_alertas", "guardar_y_recalcular_alertas"}:
            try:
                resultado = actualizar_reglas_alertas(request.POST)
                cantidad = resultado["cantidad"]
                modo_recalculo = resultado["modo_recalculo"]

                if cantidad == 0:
                    messages.info(request, "No se detectaron cambios en las reglas.")
                elif accion == "guardar_y_recalcular_alertas":
                    hilo = iniciar_recalculo_en_segundo_plano(
                        modo_recalculo=modo_recalculo
                    )
                    if hilo is None:
                        messages.warning(
                            request,
                            f"Se guardaron {cantidad} regla(s), pero ya hay un "
                            "recálculo manual en curso. No se inició otro proceso.",
                        )
                    else:
                        descripcion_modo = (
                            "completo, porque cambió una regla de detección"
                            if modo_recalculo == "completo"
                            else "rápido, porque solo cambiaron reglas de clasificación"
                        )
                        messages.success(
                            request,
                            f"Se guardaron {cantidad} regla(s). Se inició el recálculo "
                            f"{descripcion_modo} en segundo plano.",
                        )
                else:
                    messages.success(
                        request,
                        f"Se guardaron {cantidad} regla(s) y se validaron en Oracle.",
                    )
            except ValueError as error:
                messages.error(request, str(error))
            except Exception as error:
                messages.error(request, f"No fue posible actualizar las reglas: {error}")

            url_perfil = reverse("dashboard:panel_perfil")
            return redirect(f"{url_perfil}?editor_reglas=1")

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
            "puede_editar_reglas": usuario_puede_editar_reglas(usuario_actual),
        })

    return render(request, "dashboard/panel_perfil.html", context)


@login_required
def editor_reglas_alertas(request):
    """Renderiza el editor bajo demanda para no consultar Oracle al abrir el perfil."""
    if request.method != "GET":
        return HttpResponse("Método no permitido.", status=405)

    if not usuario_puede_editar_reglas(request.user):
        return HttpResponse("No tienes permisos para editar estas reglas.", status=403)

    contexto = {
        "editor_reglas": {"BATERIA": [], "GPS": []},
        "recalculo_en_curso": recalculo_en_curso(),
        "log_recalculo": leer_log_recalculo(),
    }
    estado = 200
    try:
        editor = obtener_editor_reglas_alertas()
        contexto["editor_reglas"] = editor
        contexto["total_reglas_editor"] = sum(
            len(seccion["reglas"])
            for secciones in editor.values()
            for seccion in secciones
        )
    except Exception as error:
        contexto["reglas_alertas_error"] = str(error)
        estado = 503

    return render(
        request,
        "dashboard/partials/editor_reglas_alertas.html",
        contexto,
        status=estado,
    )


@login_required
def exportar_baterias_excel(request):
    """
    Exporta el Excel estándar del AMID desde el botón Baterías.

    Por ahora:
    - siempre exporta 14 días completos
    - horario completo 00:00 a 23:30
    """

    amid = request.GET.get("amid", "").strip()

    if not amid:
        return HttpResponse("Debe indicar un AMID para exportar.", status=400)

    dias = 14
    hora_inicio = "00:00"
    hora_fin = "23:30"

    try:
        wb = crear_excel_completo_amid(
            amid=amid,
            dias=dias,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
        )
    except ValueError:
        return HttpResponse("El AMID ingresado no es válido.", status=400)
    except Exception as error:
        return HttpResponse(
            f"Error consultando datos en Oracle: {error}",
            status=500,
        )

    if wb is None:
        return HttpResponse(
            f"No existen registros para el AMID {amid} en los últimos 14 días.",
            status=404,
        )

    contenido_excel = serializar_excel(wb, cerrar=True)

    fecha_exportacion = obtener_ahora_referencia().strftime("%Y%m%d_%H%M%S")
    filename = f"datos_amid_{amid}_14_dias_{fecha_exportacion}.xlsx"

    response = HttpResponse(
        contenido_excel,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response
