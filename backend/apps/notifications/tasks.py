"""Notification tasks.

notify_incident_event(event_id)
    Fans an IncidentEvent out into one NotificationDelivery row per recipient and channel.
    Rows are keyed by a unique dedupe_key, so running it twice creates nothing new.

deliver_notification(delivery_id)
    Sends one delivery. It locks the row (NOWAIT) and skips rows that are already final,
    so a duplicate or redelivered task never sends twice. Transient failures retry with
    backoff; when retries run out the row is marked failed.
"""

import logging

from celery import shared_task
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from apps.incidents.models import IncidentEvent
from opsdesk_tasks.base import OpsDeskTask

from . import channels
from .messages import NOTIFYING_EVENTS, message_for, recipients_for
from .models import FINAL_STATUSES, Channel, DeliveryStatus, NotificationDelivery

logger = logging.getLogger(__name__)


def dedupe_key(event: IncidentEvent, user_id: int, channel: str) -> str:
    return f"event:{event.pk}:user:{user_id}:{channel}"


@shared_task(name="notifications.notify_incident_event", base=OpsDeskTask)
def notify_incident_event(event_id: int) -> dict:
    event = IncidentEvent.objects.select_related("incident", "actor").filter(pk=event_id).first()
    if event is None:  # incident deleted since: nothing to say
        return {"status": "missing"}
    if event.event_type not in NOTIFYING_EVENTS:
        return {"status": "ignored"}

    message = message_for(event)
    pending_ids = []
    for user in recipients_for(event):
        for channel in Channel.values:
            key = dedupe_key(event, user.pk, channel)
            try:
                with transaction.atomic():
                    delivery, _ = NotificationDelivery.objects.get_or_create(
                        dedupe_key=key,
                        defaults={
                            "recipient": user,
                            "incident": event.incident,
                            "kind": message.kind,
                            "channel": channel,
                            "subject": message.subject,
                            "body": message.body,
                        },
                    )
            except IntegrityError:  # another worker created it between our get and create
                delivery = NotificationDelivery.objects.get(dedupe_key=key)
            # Also re-send rows still pending from an earlier run that died before sending.
            if delivery.status == DeliveryStatus.PENDING:
                pending_ids.append(delivery.pk)

    for pk in pending_ids:
        deliver_notification.delay(pk)
    return {"status": "fanned_out", "deliveries": len(pending_ids)}


class DeliverTask(OpsDeskTask):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        super().on_failure(exc, task_id, args, kwargs, einfo)
        delivery_id = kwargs.get("delivery_id") or (args[0] if args else None)
        NotificationDelivery.objects.filter(pk=delivery_id, status=DeliveryStatus.PENDING).update(
            status=DeliveryStatus.FAILED, last_error=repr(exc)[:2000]
        )


@shared_task(name="notifications.deliver", base=DeliverTask)
def deliver_notification(delivery_id: int) -> str:
    error: Exception | None = None
    try:
        with transaction.atomic():
            delivery = (
                NotificationDelivery.objects.select_for_update(nowait=True, of=("self",))
                .select_related("recipient", "incident")
                .filter(pk=delivery_id)
                .first()
            )
            if delivery is None:
                return "missing"
            if delivery.status in FINAL_STATUSES:
                logger.info(
                    "duplicate delivery skipped",
                    extra={"delivery_id": delivery_id, "status": delivery.status},
                )
                return "duplicate"
            if not delivery.recipient.is_active:
                delivery.status = DeliveryStatus.SKIPPED
                delivery.save(update_fields=["status"])
                return "skipped"

            delivery.attempts += 1
            try:
                result = channels.SENDERS[delivery.channel](delivery)
            except channels.PermanentDeliveryError as exc:
                delivery.status, delivery.last_error = DeliveryStatus.FAILED, str(exc)[:2000]
                delivery.save(update_fields=["status", "attempts", "last_error"])
                logger.error(
                    "delivery failed permanently",
                    extra={"delivery_id": delivery_id, "error": str(exc)},
                )
                return "failed"
            except Exception as exc:  # noqa: BLE001 - recorded, then retried below
                delivery.last_error = repr(exc)[:2000]
                delivery.save(update_fields=["attempts", "last_error"])
                error = exc
            else:
                delivery.status, delivery.sent_at = DeliveryStatus.SENT, timezone.now()
                if result is not None:
                    delivery.notification = result
                delivery.save(update_fields=["status", "sent_at", "attempts", "notification"])
                return "sent"
    except DatabaseError as exc:
        if "could not obtain lock" in str(exc) or "LockNotAvailable" in repr(exc.__cause__):
            # Another worker is sending this right now; it owns the outcome.
            logger.info("delivery busy elsewhere", extra={"delivery_id": delivery_id})
            return "busy"
        raise

    # Outside the transaction, so the attempt count and error above are kept.
    raise error
