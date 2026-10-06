from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

from apps.dashboard.autenticacion import LoginConRecordarView

urlpatterns = [
    path("admin/", admin.site.urls),

    path(
        "login/",
        LoginConRecordarView.as_view(),
        name="login"
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout"
    ),

    path(
        "transacciones/",
        include(
            ("apps.transacciones.urls", "transacciones"),
            namespace="transacciones",
        ),
    ),

    path(
        "plantillas-excel/",
        include(
            ("apps.excel_templates.urls", "excel_templates"),
            namespace="excel_templates",
        ),
    ),

    path("", include(("apps.dashboard.urls", "dashboard"), namespace="dashboard")),
    path(
        "password_change/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            success_url="/password_change/done/"
        ),
        name="password_change"
    ),

    path(
        "password_change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html"
        ),
        name="password_change_done"
    ),
]