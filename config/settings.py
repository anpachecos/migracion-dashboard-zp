from pathlib import Path
import os

from dotenv import load_dotenv


# =========================
# Rutas base
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


# =========================
# Seguridad / entorno
# =========================

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-dev-key")
DEBUG = os.getenv("DEBUG", "True") == "True"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "ALLOWED_HOSTS",
        "localhost,127.0.0.1"
    ).split(",")
    if host.strip()
]


# =========================
# Aplicaciones instaladas
# =========================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # App propia
    "apps.dashboard.apps.DashboardConfig",
]


# =========================
# Middleware
# =========================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# =========================
# URLs / WSGI
# =========================

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


# =========================
# Templates
# =========================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.dashboard.context_processors.datos_actualizacion_dashboard",
            ],
        },
    },
]


# =========================
# Base de datos local Django
# =========================
# SQLite se usa para datos internos de Django:
# usuarios, grupos, permisos, sesiones, migraciones y logs internos.
# Los datos operativos del dashboard se consultan desde Oracle.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 30,
        },
    }
}


# =========================
# Validación de contraseñas
# =========================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# =========================
# Idioma / zona horaria
# =========================

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"

USE_I18N = True
USE_TZ = True


# =========================
# Archivos estáticos
# =========================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# =========================
# Oracle
# =========================
# La conexión Oracle se realiza desde services/oracle_connection.py.
# Aquí solo se leen las variables de entorno necesarias.

ORACLE_HOST = os.getenv("ORACLE_HOST")
ORACLE_PORT = int(os.getenv("ORACLE_PORT", "1521"))
ORACLE_SERVICE_NAME = os.getenv("ORACLE_SERVICE_NAME")
ORACLE_USER = os.getenv("ORACLE_USER")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD")
ORACLE_CLIENT_PATH = os.getenv("ORACLE_CLIENT_PATH")


# =========================
# Autenticación / sesiones
# =========================

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:panel_baterias"
LOGOUT_REDIRECT_URL = "login"

# 2 horas de sesión
SESSION_COOKIE_AGE = 60 * 60 * 2

# Renueva la sesión si el usuario sigue usando el dashboard
SESSION_SAVE_EVERY_REQUEST = True

# Cierra sesión al cerrar el navegador
SESSION_EXPIRE_AT_BROWSER_CLOSE = True


# =========================
# Caché local
# =========================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "dashboard-zp-cache",
    }
}


# =========================
# Scheduler interno
# =========================
# Desactivado por defecto.
# Antes de activarlo, revisar apps/dashboard/services/scheduler.py,
# porque puede contener jobs del flujo antiguo SQLite.

DASHBOARD_SCHEDULER_ENABLED = os.getenv(
    "DASHBOARD_SCHEDULER_ENABLED",
    "False"
) == "True"