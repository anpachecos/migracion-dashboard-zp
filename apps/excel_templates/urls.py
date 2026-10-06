from django.urls import path

from . import views

app_name = "excel_templates"

urlpatterns = [
    path("", views.listar_plantillas, name="listar"),
    path("capturar/", views.capturar_plantilla, name="capturar"),
    path("<int:plantilla_id>/editar/", views.editar_plantilla, name="editar"),
    path("<int:plantilla_id>/exportar/", views.exportar_plantilla, name="exportar"),
]
