from pathlib import Path
import os

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured


# =========================
# Rutas base
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


# =========================
# Seguridad / entorno
# =========================

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY or not SECRET_KEY.strip():
    raise ImproperlyConfigured(
        "SECRET_KEY debe estar definida en las variables de entorno."
    )


def obtener_debug_desde_entorno():
    valor = os.getenv("DEBUG")

    if valor is None:
        return False

    valor_normalizado = valor.strip().lower()

    if valor_normalizado in {"true", "1", "yes", "on"}:
        return True

    if valor_normalizado in {"false", "0", "no", "off"}:
        return False

    raise ImproperlyConfigured(
        "DEBUG debe usar uno de estos valores: "
        "true, 1, yes, on, false, 0, no u off."
    )


DEBUG = obtener_debug_desde_entorno()

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "ALLOWED_HOSTS",
        "localhost,127.0.0.1"
    ).split(",")
    if host.strip()
]


# =========================
# Identidad de la aplicación
# =========================

# Versión mostrada al usuario. Es la única fuente de verdad: el pie del
# sidebar y el login la toman de acá, no de una copia escrita en el HTML.
# Subirla es parte del cambio, igual que en cualquier aplicación visible.
VERSION_APP = "1.4.0"

AMBIENTES_VALIDOS = ("DESARROLLO", "PRE", "PRODUCCION")


def obtener_ambiente_desde_entorno():
    """
    Nombre del entorno donde corre la aplicación.

    Se valida en vez de acceptarse cualquier texto porque el valor se
    muestra en pantalla: una etiqueta equivocada induce a operar sobre
    el entorno que no es. Mismo criterio fail-closed que DEBUG.
    """

    valor = os.getenv("AMBIENTE", "DESARROLLO").strip().upper()

    if valor not in AMBIENTES_VALIDOS:
        raise ImproperlyConfigured(
            "AMBIENTE debe usar uno de estos valores: "
            "DESARROLLO, PRE o PRODUCCION."
        )

    return valor


AMBIENTE = obtener_ambiente_desde_entorno()


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
    "apps.transacciones.apps.TransaccionesConfig",
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
                "apps.dashboard.context_processors.metadatos_app",
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

# Sesión persistente del checkbox "Recordarme" del login.
# Al marcar la opción la sesión dura esta cantidad de días aunque se cierre
# el navegador. Sin marcar aplica SESSION_EXPIRE_AT_BROWSER_CLOSE.
SESION_RECORDAR_DIAS = 30


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
# Validación Version_DB
# =========================
# Límites operativos versionados. Se expresan en bytes o cantidades y pueden
# ajustarse por entorno de prueba con override_settings() al crecer el volumen.

VERSION_ZP_MAX_FILE_BYTES = 5 * 1024 * 1024
VERSION_ZP_MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
VERSION_ZP_MAX_ROWS = 5000
VERSION_ZP_MAX_COLUMNS = 100
VERSION_ZP_MAX_COMPRESSION_RATIO = 100


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


ALERTAS_RECALCULO_DURABLE_ENABLED = os.getenv(
    "ALERTAS_RECALCULO_DURABLE_ENABLED",
    "False",
).strip().lower() in {"true", "1", "yes", "on"}



# =========================
# Módulo de Transacciones (TRX C2D)
# =========================
# El módulo de Transacciones es de solo lectura: consulta Oracle bajo demanda
# y no crea objetos, tablas ni jobs. Permanece apagado hasta validar el
# universo del dataset contra los Excel de referencia del Informe Interno.

# Apagado por defecto. El panel funciona como estructura sin consultar Oracle.
TRX_ORACLE_HABILITADO = os.getenv(
    "TRX_ORACLE_HABILITADO",
    "False",
).strip().lower() in {"true", "1", "yes", "on"}

# Universo ZP. Correlato de AMID_MINIMO_ALERTAS del panel de alertas.
TRX_AMID_MINIMO = int(os.getenv("TRX_AMID_MINIMO", "7500000"))

# Límite operativo versionado. La fuente TRX tiene alto volumen: no se cargan
# rangos amplios sin filtro explícito.
TRX_RANGO_MAXIMO_DIAS = int(os.getenv("TRX_RANGO_MAXIMO_DIAS", "7"))
TRX_FILAS_POR_PAGINA = int(os.getenv("TRX_FILAS_POR_PAGINA", "200"))
TRX_MAX_FILAS_DETALLE = int(os.getenv("TRX_MAX_FILAS_DETALLE", "2000"))

# Día base del filtro de fechas: "trx" (día de la TRX) o "bd" (día de llegada).
# Ver docs/09_transacciones_trx.md, supuesto S1.
TRX_MODO_FECHA_BASE = os.getenv("TRX_MODO_FECHA_BASE", "trx")

# Grupos de Django con acceso al módulo de Transacciones, separados por coma.
# La política vive en configuración y no en el código para no requerir un
# despliegue al cambiar quién entra. Deben coincidir EXACTAMENTE con los
# nombres de `auth_group`: la comparación es case-sensitive, "SONDA" no es
# "Sonda". Vaciar la lista deja el módulo únicamente para superusuarios.
TRX_GRUPOS_PERMITIDOS = tuple(
    grupo.strip()
    for grupo in os.getenv("TRX_GRUPOS_PERMITIDOS", "Admin,SONDA").split(",")
    if grupo.strip()
)
