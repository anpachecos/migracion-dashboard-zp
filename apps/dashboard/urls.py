from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.panel_baterias, name="panel_baterias"),
    path("baterias/", views.panel_baterias, name="panel_baterias"),
    path("gps/", views.panel_gps, name="panel_gps"),
    path("alertas/", views.panel_alertas, name="panel_alertas"),
    path("perfil/", views.panel_perfil, name="panel_perfil"),
    path("perfil/ejecutar-comando/", views.ejecutar_comando_admin, name="ejecutar_comando_admin"),
    path("baterias/exportar/", views.exportar_baterias_excel, name="exportar_baterias_excel"),
    path("alertas/exportar/", views.exportar_alertas_excel, name="exportar_alertas_excel"),
    path("gps/exportar/", views.exportar_gps_excel, name="exportar_gps_excel"),
]
