"""Local development settings. Safe placeholder defaults so `runserver` just works."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key-change-me")
os.environ.setdefault("JWT_SIGNING_KEY", "dev-only-insecure-jwt-signing-key-change-me")
os.environ.setdefault("DATABASE_URL", "postgres://opsdesk:opsdesk@localhost:5432/opsdesk")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DJANGO_READ_DOT_ENV_FILE", "true")

from .base import *  # noqa: E402, F403
from .base import env  # noqa: E402

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
APP_ENV = "development"
ALLOW_REGISTRATION = env.bool("ALLOW_REGISTRATION", default=True)
REFRESH_COOKIE_SECURE = env.bool("REFRESH_COOKIE_SECURE", default=False)
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"])
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
LOGGING["handlers"]["console"]["formatter"] = env("LOG_FORMAT", default="plain")  # noqa: F405
