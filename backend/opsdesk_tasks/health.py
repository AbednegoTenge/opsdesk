"""Liveness heartbeats for the worker and Beat processes.

Each process touches a file on a timer. A probe (`python -m opsdesk_tasks.healthcheck`)
reports unhealthy when the file is older than a threshold, which catches a hung process
that is still alive but no longer doing work.
"""

import logging
from pathlib import Path

from celery import bootsteps
from celery.beat import PersistentScheduler

logger = logging.getLogger(__name__)


def touch(path: str) -> None:
    try:
        Path(path).touch()
    except OSError as exc:
        logger.warning("could not write heartbeat file", extra={"path": path, "error": str(exc)})


class WorkerHeartbeat(bootsteps.StartStopStep):
    """Touches WORKER_HEARTBEAT_FILE every WORKER_HEARTBEAT_INTERVAL seconds."""

    requires = {"celery.worker.components:Timer"}

    def __init__(self, worker, **kwargs):
        super().__init__(worker, **kwargs)
        self.tref = None

    def start(self, worker):
        from django.conf import settings

        path, interval = settings.WORKER_HEARTBEAT_FILE, settings.WORKER_HEARTBEAT_INTERVAL
        touch(path)
        self.tref = worker.timer.call_repeatedly(interval, touch, (path,), priority=10)

    def stop(self, worker):
        if self.tref:
            self.tref.cancel()
            self.tref = None


class HeartbeatScheduler(PersistentScheduler):
    """Beat scheduler that touches BEAT_HEARTBEAT_FILE on every tick."""

    def tick(self, *args, **kwargs):
        from django.conf import settings

        touch(settings.BEAT_HEARTBEAT_FILE)
        return super().tick(*args, **kwargs)
