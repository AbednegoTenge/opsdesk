"""Settings shared by every process (API, Celery worker, Celery Beat).

Every value that differs between environments comes from an environment variable.
Nothing here may hold a real secret.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
if env.bool("DJANGO_READ_DOT_ENV_FILE", default=False):
    env.read_env(str(BASE_DIR / ".env"))

# --- Core -----------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
APP_ENV = env("APP_ENV", default="production")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "apps.core",
    "apps.users",
    "apps.incidents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

# --- Database -------------------------------------------------------------
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"].setdefault("OPTIONS", {})
DATABASES["default"]["OPTIONS"].setdefault(
    "connect_timeout", env.int("DB_CONNECT_TIMEOUT", default=5)
)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Redis ----------------------------------------------------------------
REDIS_URL = env("REDIS_URL")
REDIS_SOCKET_TIMEOUT = env.float("REDIS_SOCKET_TIMEOUT", default=2.0)

# --- Auth -----------------------------------------------------------------
AUTH_USER_MODEL = "users.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

ALLOW_REGISTRATION = env.bool("ALLOW_REGISTRATION", default=False)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_TTL_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_TTL_DAYS", default=7)),
    "ALGORITHM": env("JWT_ALGORITHM", default="HS256"),
    # Shared by every API replica so any replica can verify any token.
    "SIGNING_KEY": env("JWT_SIGNING_KEY"),
    "ISSUER": env("JWT_ISSUER", default="opsdesk"),
    "AUDIENCE": env("JWT_AUDIENCE", default="opsdesk-api"),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "UPDATE_LAST_LOGIN": True,
    # Rotation and revocation are handled by apps.users.token_store (Redis).
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
}

# Refresh token cookie (httpOnly, never readable by JavaScript).
REFRESH_COOKIE_NAME = env("REFRESH_COOKIE_NAME", default="opsdesk_refresh")
REFRESH_COOKIE_SECURE = env.bool("REFRESH_COOKIE_SECURE", default=True)
REFRESH_COOKIE_SAMESITE = env("REFRESH_COOKIE_SAMESITE", default="Lax")
REFRESH_COOKIE_DOMAIN = env("REFRESH_COOKIE_DOMAIN", default=None)
REFRESH_COOKIE_PATH = "/api/v1/auth/"
REFRESH_TOKEN_KEY_PREFIX = env("REFRESH_TOKEN_KEY_PREFIX", default="opsdesk:refresh")

# --- CORS -----------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True  # needed for the refresh-token cookie
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=CORS_ALLOWED_ORIGINS)

# --- DRF ------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "OpsDesk API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --- Email ----------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="OpsDesk <no-reply@example.com>")

# --- I18N / static --------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Health checks --------------------------------------------------------
HEALTH_DB_TIMEOUT_MS = env.int("HEALTH_DB_TIMEOUT_MS", default=2000)

# --- Logging (JSON to stdout, one line per record) -------------------------
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "apps.core.logging.JsonFormatter"},
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": env("LOG_FORMAT", default="json"),
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
    },
}
