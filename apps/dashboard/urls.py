from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.panel_baterias, name="panel_baterias"),
    path("baterias/", views.panel_baterias, name="panel_baterias"),
    path("gps/", views.panel_gps, name="panel_gps"),
    path("alertas/", views.panel_alertas, name="panel_alertas"),
    path("perfil/", views.panel_perfil, name="panel_perfil"),
    path("baterias/exportar/", views.exportar_baterias_excel, name="exportar_baterias_excel"),
]
