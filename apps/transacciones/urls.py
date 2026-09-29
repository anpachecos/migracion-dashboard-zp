from django.urls import path

from . import views


app_name = "transacciones"

urlpatterns = [
    # La raíz redirige al informe interno, que es el candidato a validar
    # primero contra los Excel de referencia.
    path("", views.inicio, name="inicio"),
    path("informe-interno/", views.informe_interno, name="informe_interno"),
    path("mayor-15/", views.mayor_15, name="mayor_15"),
    path("rezagadas/", views.rezagadas, name="rezagadas"),
]
