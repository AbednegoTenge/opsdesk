"""Celery application shared by the worker and Beat processes.

The API process imports this module only to *send* tasks; it never runs them.
Run with:
    celery -A config worker -Q notifications,sla,reports
    celery -A config beat
"""

import os

from celery import Celery
from kombu import Queue

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

app = Celery("opsdesk")
app.config_from_object("django.conf:settings", namespace="CELERY")

app.conf.task_queues = (
    Queue("notifications"),
    Queue("sla"),
    Queue("reports"),
)
app.conf.task_default_queue = "notifications"
app.conf.task_routes = {
    "notifications.*": {"queue": "notifications"},
    "outbox.*": {"queue": "notifications"},
    "sla.*": {"queue": "sla"},
    "reporting.*": {"queue": "reports"},
}

app.autodiscover_tasks(["apps.notifications", "apps.sla", "apps.reporting", "opsdesk_tasks"])

# Worker liveness heartbeat (see opsdesk_tasks/health.py).
from opsdesk_tasks.health import WorkerHeartbeat  # noqa: E402

app.steps["worker"].add(WorkerHeartbeat)
