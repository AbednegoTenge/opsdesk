"""Test settings: real PostgreSQL (tests rely on its transaction behaviour), fake Redis."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SIGNING_KEY", "test-jwt-signing-key-at-least-32-bytes-long")
os.environ.setdefault("DATABASE_URL", "postgres://opsdesk:opsdesk@localhost:5432/opsdesk")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

from .base import *  # noqa: E402, F403

DEBUG = False
APP_ENV = "test"
ALLOWED_HOSTS = ["testserver", "localhost"]
ALLOW_REGISTRATION = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
LOGGING["root"]["level"] = "WARNING"  # noqa: F405

# Tasks run inline when published. Failures are kept on the result, not raised into the
# caller, as in production where the API never sees worker errors.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BROKER_URL = "memory://"
TASK_RETRY_BACKOFF_MAX = 0
