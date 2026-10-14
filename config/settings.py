"""Django settings for PolyMentor.

Single, env-driven settings module (no multi-settings sprawl). Reads a local
`.env` in development via python-dotenv. Secrets never live in code.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env for local development (no-op if the file is absent, e.g. in prod).
load_dotenv(BASE_DIR / ".env")


def env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def env_list(key: str, default: str = "") -> list[str]:
    raw = os.environ.get(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Core -----------------------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-secret-key")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000",
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "django_htmx",
    # Local
    "apps.core",
    "apps.corpora",
    "apps.experts",
    "apps.routing",
    "apps.aggregation",
    "apps.sessions",
    "apps.feedback",
    "apps.alignment",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database -------------------------------------------------------------
# SQLite by default for frictionless local dev; Postgres via DATABASE_URL in prod.
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    # Minimal parser to avoid an extra dependency; supports postgres URLs.
    from urllib.parse import urlparse

    parsed = urlparse(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
            "CONN_MAX_AGE": 600,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- Auth / passwords ------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- I18N ------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --- Static ----------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF -------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
}

# --- Celery ----------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", True)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE

# --- Nugen -----------------------------------------------------------------
NUGEN_API_KEY = os.environ.get("NUGEN_API_KEY", "")
NUGEN_BASE_URL = os.environ.get("NUGEN_BASE_URL", "https://api.nugen.in")
NUGEN_DEFAULT_MODEL = os.environ.get("NUGEN_DEFAULT_MODEL", "")
NUGEN_DAILY_SPEND_USD = float(os.environ.get("NUGEN_DAILY_SPEND_USD", "12") or 12)

# --- Admin console ---------------------------------------------------------
ADMIN_BEARER_TOKEN = os.environ.get("ADMIN_BEARER_TOKEN", "")

# --- Logging ---------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": '{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
        },
        "plain": {"format": "%(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "plain" if DEBUG else "json",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "polymentor": {"handlers": ["console"], "level": "DEBUG" if DEBUG else "INFO", "propagate": False},
    },
}
