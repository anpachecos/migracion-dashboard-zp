from django.shortcuts import render

from .services.baterias_service import obtener_contexto_baterias
from .services.gps_service import obtener_contexto_gps


def panel_baterias(request):
    contexto = obtener_contexto_baterias(request)
    contexto["active_page"] = "baterias"
    return render(request, "dashboard/panel_baterias.html", contexto)


def panel_gps(request):
    contexto = obtener_contexto_gps(request)
    contexto["active_page"] = "gps"
    return render(request, "dashboard/panel_gps.html", contexto)


def panel_alertas(request):
    return render(request, "dashboard/panel_alertas.html", {
        "active_page": "alertas",
    })


def panel_perfil(request):
    return render(request, "dashboard/panel_perfil.html", {
        "active_page": "perfil",
    })