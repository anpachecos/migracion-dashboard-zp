from django.urls import path

from . import views


app_name = "dashboard"

urlpatterns = [
    # Panel principal
    path("", views.panel_baterias, name="inicio"),

    # Paneles
    path("baterias/", views.panel_baterias, name="panel_baterias"),
    path("gps/", views.panel_gps, name="panel_gps"),
    path("alertas/", views.panel_alertas, name="panel_alertas"),
    path(
        "alertas/buscar-exclusiones/",
        views.buscar_exclusiones_alertas,
        name="buscar_exclusiones_alertas",
    ),
    path(
        "alertas/caidas-bateria/",
        views.detalle_caidas_bateria,
        name="detalle_caidas_bateria",
    ),
    path("perfil/", views.panel_perfil, name="panel_perfil"),
    path(
        "perfil/reglas-alertas/editor/",
        views.editor_reglas_alertas,
        name="editor_reglas_alertas",
    ),

    # Acciones administrativas
    path(
        "perfil/ejecutar-comando/",
        views.ejecutar_comando_admin,
        name="ejecutar_comando_admin",
    ),

    # Exportaciones
    path(
        "baterias/exportar/",
        views.exportar_baterias_excel,
        name="exportar_baterias_excel",
    ),
    path(
        "gps/exportar/",
        views.exportar_gps_excel,
        name="exportar_gps_excel",
    ),
    path(
        "alertas/exportar/",
        views.exportar_alertas_excel,
        name="exportar_alertas_excel",
    ),
]