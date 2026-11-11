"""Base class for every OpsDesk task: retries with backoff for transient errors, and logging."""

import logging
import smtplib
import socket

import redis
from celery import Task
from django.conf import settings
from django.db import InterfaceError, OperationalError

logger = logging.getLogger("opsdesk.tasks")

# Errors worth retrying: the dependency may be back in a moment.
TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    OperationalError,
    InterfaceError,
    redis.ConnectionError,
    redis.TimeoutError,
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
    smtplib.SMTPHeloError,
    ConnectionError,
    TimeoutError,
    socket.timeout,
)


class TransientTaskError(Exception):
    """Raise from a task to request a retry for a failure not covered above."""


class OpsDeskTask(Task):
    autoretry_for = (*TRANSIENT_ERRORS, TransientTaskError)
    retry_backoff = 2  # 2s, 4s, 8s, ... capped by retry_backoff_max
    retry_jitter = True
    acks_late = True

    @property
    def max_retries(self):  # read at call time so settings overrides apply
        return settings.TASK_MAX_RETRIES

    @property
    def retry_backoff_max(self):
        return settings.TASK_RETRY_BACKOFF_MAX

    def _ctx(self, task_id, args, kwargs, **extra):
        return {
            "task": self.name,
            "task_id": task_id,
            "task_kwargs": kwargs,
            "retries": self.request.retries if self.request else None,
            **extra,
        }

    def before_start(self, task_id, args, kwargs):
        logger.info("task started", extra=self._ctx(task_id, args, kwargs))

    def on_success(self, retval, task_id, args, kwargs):
        logger.info("task succeeded", extra=self._ctx(task_id, args, kwargs, result=retval))

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning("task retrying", extra=self._ctx(task_id, args, kwargs, error=repr(exc)))

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "task failed",
            extra=self._ctx(task_id, args, kwargs, error=repr(exc)),
            exc_info=(type(exc), exc, exc.__traceback__),
        )
