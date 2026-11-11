"""Liveness and readiness probes. Unversioned and unauthenticated by design."""

import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.core.redis_client import get_redis

logger = logging.getLogger(__name__)


@require_GET
def live(request):
    """The process is up and can answer HTTP. No dependency checks."""
    return JsonResponse({"status": "ok"})


def _check_database() -> tuple[bool, str | None]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = %s", [settings.HEALTH_DB_TIMEOUT_MS])
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True, None
    except Exception as exc:  # noqa: BLE001 - any failure means not ready
        logger.warning("readiness: database check failed", extra={"error": str(exc)})
        connection.close_if_unusable_or_obsolete()
        return False, exc.__class__.__name__


def _check_redis() -> tuple[bool, str | None]:
    try:
        get_redis().ping()
        return True, None
    except Exception as exc:  # noqa: BLE001
        logger.warning("readiness: redis check failed", extra={"error": str(exc)})
        return False, exc.__class__.__name__


@require_GET
def ready(request):
    """Ready to serve traffic: PostgreSQL is required, Redis is reported.

    Redis is not required because most requests (anything with a valid access token)
    work without it; only token refresh, logout and task enqueueing degrade.
    """
    db_ok, db_error = _check_database()
    redis_ok, redis_error = _check_redis()
    body = {
        "status": "ok" if db_ok else "unavailable",
        "checks": {
            "database": {"ok": db_ok, "error": db_error},
            "redis": {"ok": redis_ok, "error": redis_error, "required": False},
        },
    }
    return JsonResponse(body, status=200 if db_ok else 503)
