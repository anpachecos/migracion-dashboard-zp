from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("baterias/", views.panel_baterias, name="panel_baterias"),
]