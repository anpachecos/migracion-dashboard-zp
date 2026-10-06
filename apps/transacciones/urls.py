from django.urls import path

from . import views


app_name = "transacciones"

urlpatterns = [
    # El monitor es una sola página con cuatro pestañas. Las rutas que
    # existían por pestaña quedan como redirecciones para que los enlaces
    # ya compartidos sigan llevando a la pestaña correcta.
    path("", views.inicio, name="inicio"),
    path("monitor/", views.monitor, name="monitor"),
    path("centro-archivos/", views.centro_archivos, name="centro_archivos"),
    path("informe-interno/", views.informe_interno, name="informe_interno"),
    path("mayor-15/", views.mayor_15, name="mayor_15"),
    path("rezagadas/", views.rezagadas, name="rezagadas"),
]
