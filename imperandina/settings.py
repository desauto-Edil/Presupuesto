"""
Django settings for imperandina project.

Lee configuración desde variables de entorno (archivo .env en la raíz del proyecto).
Instalar python-decouple: pip install python-decouple
"""

import os
from pathlib import Path

# Intentar usar python-decouple; fallback a os.environ si no está instalado
try:
    from decouple import config, Csv
    _use_decouple = True
except ImportError:
    _use_decouple = False

    def config(key, default=None, cast=None):  # type: ignore[misc]
        val = os.environ.get(key, default)
        if val is not None and cast is not None:
            return cast(val)
        return val

    class Csv:  # type: ignore[no-redef]
        def __new__(cls):
            return lambda v: [x.strip() for x in v.split(",") if x.strip()]


# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar .env manualmente si decouple no está disponible
if not _use_decouple:
    _env_file = BASE_DIR / ".env"
    if _env_file.exists():
        with open(_env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


# ---------------------------------------------------------------------------
# Seguridad
# ---------------------------------------------------------------------------

def _require_env(key: str) -> str:
    """Falla con mensaje claro si una variable de entorno obligatoria no está definida."""
    value = config(key, default=None)
    if not value:
        raise RuntimeError(
            f"\n\n[IMPERANDINA] Variable de entorno obligatoria no definida: {key}\n"
            f"Crea o revisa el archivo .env y define {key}=<valor>.\n"
            f"Consulta .env.example para la lista completa de variables requeridas.\n"
        )
    return value


SECRET_KEY = _require_env("SECRET_KEY")

DEBUG = config("DEBUG", default=False, cast=bool)

_allowed = config("ALLOWED_HOSTS", default="localhost,127.0.0.1")
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(",") if h.strip()]


# ---------------------------------------------------------------------------
# Aplicaciones instaladas
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # ── Apps por dominio de negocio ──────────────────────────────────────────
    "apps.common",
    "apps.configuracion",
    "apps.catalogos",
    "apps.ingenieria",
    "apps.comercial",
    "apps.presupuestos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.configuracion.middleware.AuthCustomMiddleware",
]

ROOT_URLCONF = "imperandina.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "imperandina.wsgi.application"


# ---------------------------------------------------------------------------
# Base de datos — PostgreSQL
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="presupuestos"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": _require_env("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}


# ---------------------------------------------------------------------------
# Validación de contraseñas
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# Internacionalización
# ---------------------------------------------------------------------------
LANGUAGE_CODE = config("LANGUAGE_CODE", default="es-co")
TIME_ZONE     = config("TIME_ZONE",     default="America/Bogota")
USE_I18N = True
USE_TZ   = True


# ---------------------------------------------------------------------------
# Archivos estáticos
# ---------------------------------------------------------------------------
STATIC_URL   = "/static/"
STATIC_ROOT  = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ---------------------------------------------------------------------------
# Clave primaria por defecto
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Cache (Fase 0 — base arquitectónica)
# ---------------------------------------------------------------------------
# Desarrollo: LocMemCache (por defecto).
# Producción: definir CACHE_BACKEND=redis y REDIS_URL=redis://host:6379/1 en .env.
#
# La política de uso (cache-aside, TTLs, namespaces, invalidación) vive en
# apps/common/cache.py — settings.py solo declara el backend.
_CACHE_BACKEND = config("CACHE_BACKEND", default="locmem")

if _CACHE_BACKEND == "redis":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": config("REDIS_URL", default="redis://127.0.0.1:6379/1"),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "andinacost-dev",
        }
    }


# ---------------------------------------------------------------------------
# Seguridad HTTP (producción)
# Todos por defecto apagados para no romper desarrollo local sin HTTPS.
# En producción activar en .env:
#   SECURE_SSL_REDIRECT=True
#   SESSION_COOKIE_SECURE=True
#   CSRF_COOKIE_SECURE=True
#   SECURE_HSTS_SECONDS=31536000
#   SECURE_HSTS_INCLUDE_SUBDOMAINS=True
#   X_FRAME_OPTIONS=DENY
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT             = config("SECURE_SSL_REDIRECT",             default=False, cast=bool)
SESSION_COOKIE_SECURE           = config("SESSION_COOKIE_SECURE",           default=False, cast=bool)
CSRF_COOKIE_SECURE              = config("CSRF_COOKIE_SECURE",              default=False, cast=bool)
SESSION_COOKIE_HTTPONLY         = True
SECURE_HSTS_SECONDS             = config("SECURE_HSTS_SECONDS",             default=0,     cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS  = config("SECURE_HSTS_INCLUDE_SUBDOMAINS",  default=False, cast=bool)
X_FRAME_OPTIONS                 = config("X_FRAME_OPTIONS",                 default="SAMEORIGIN")

# Tamaño máximo de subida de archivos (configurable, default 10 MB)
MAX_UPLOAD_SIZE_MB = config("MAX_UPLOAD_SIZE_MB", default=10, cast=int)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_LOG_LEVEL = config("LOG_LEVEL", default="DEBUG")
_LOG_FILE  = config("LOG_FILE",  default="logs/imperandina.log")

# Crear directorio de logs si no existe
_log_dir = BASE_DIR / Path(_LOG_FILE).parent
_log_dir.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "level": _LOG_LEVEL,
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / _LOG_FILE,
            "maxBytes": 5 * 1024 * 1024,   # 5 MB
            "backupCount": 3,
            "formatter": "verbose",
            "level": _LOG_LEVEL,
            "encoding": "utf-8",
        },
    },

    "loggers": {
        # Logger raíz de apps por dominio
        "apps": {
            "handlers": ["console", "file"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        # Logger de la app legada core (se mantiene durante la transición)
        "core": {
            "handlers": ["console", "file"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        # Logger del motor de servicios (legado)
        "core.services": {
            "handlers": ["console", "file"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        # Logger de Django (SQL queries, requests)
        "django": {
            "handlers": ["console", "file"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["file"],
            "level": "ERROR",
            "propagate": False,
        },
    },

    "root": {
        "handlers": ["console", "file"],
        "level": "WARNING",
    },
}
