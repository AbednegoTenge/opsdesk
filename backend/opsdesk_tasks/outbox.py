"""Transactional outbox.

`enqueue()` is called inside a service-layer transaction. It stores the task as a row and
publishes it only after the transaction commits, so a worker never sees work for data that
was rolled back. If publishing fails (Redis down), the row stays pending for the sweep.
"""

import logging
from datetime import timedelta

from celery import signature
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import OutboxMessage, OutboxStatus

logger = logging.getLogger(__name__)


def enqueue(task_name: str, **kwargs) -> OutboxMessage:
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("outbox.enqueue() must be called inside a transaction")
    message = OutboxMessage.objects.create(task_name=task_name, payload=kwargs)
    transaction.on_commit(lambda: publish(message.pk))
    return message


def publish(message_id: int) -> bool:
    """Send one outbox row to the broker. Never raises: failures leave the row pending."""
    message = OutboxMessage.objects.filter(pk=message_id, status=OutboxStatus.PENDING).first()
    if message is None:
        return False
    try:
        signature(message.task_name, kwargs=message.payload).apply_async(
            # A stable task id makes a double publish easy to spot in logs.
            task_id=f"outbox-{message.pk}-{message.attempts}"
        )
    except Exception as exc:  # noqa: BLE001 - broker errors vary by transport
        OutboxMessage.objects.filter(pk=message.pk).update(
            attempts=message.attempts + 1, last_error=str(exc)[:2000]
        )
        logger.error(
            "outbox publish failed; will retry from sweep",
            extra={"outbox_id": message.pk, "task": message.task_name, "error": str(exc)},
        )
        return False
    OutboxMessage.objects.filter(pk=message.pk).update(
        status=OutboxStatus.SENT, dispatched_at=timezone.now(), attempts=message.attempts + 1
    )
    return True


def dispatch_pending(limit: int = 200) -> int:
    """Publish rows that missed their on-commit publish. Safe to run on many workers at once."""
    cutoff = timezone.now() - timedelta(seconds=settings.OUTBOX_RETRY_AFTER_SECONDS)
    sent = 0
    with transaction.atomic():
        ids = list(
            OutboxMessage.objects.select_for_update(skip_locked=True)
            .filter(status=OutboxStatus.PENDING, created_at__lt=cutoff)
            .order_by("created_at")
            .values_list("pk", flat=True)[:limit]
        )
        for pk in ids:
            sent += publish(pk)
    if ids:
        logger.info("outbox sweep", extra={"found": len(ids), "published": sent})
    return sent
