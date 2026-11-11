"""SLA monitoring and reminders. Called by periodic Celery tasks; safe to run concurrently.

Idempotency comes from conditional UPDATEs: a breach is recorded only by the run whose
UPDATE ... WHERE <target>_breached_at IS NULL actually changed the row, and a reminder only
by the run whose UPDATE moved last_reminded_at. Any other concurrent run changes nothing.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.incidents.models import (
    ACTIVE_STATUSES,
    EventType,
    Incident,
    SLAPolicy,
    SLAStatus,
)
from apps.incidents.services import record_system_event

logger = logging.getLogger(__name__)

# An incident is "at risk" once this share of its resolution window has passed.
AT_RISK_FRACTION = 0.75


@dataclass
class SLARunResult:
    response_breaches: list[int] = field(default_factory=list)
    resolution_breaches: list[int] = field(default_factory=list)
    at_risk: int = 0


def _flag_breach(incident_id: int, target: str, now) -> bool:
    """Atomically flag one target as breached. True only for the run that flagged it."""
    column = f"{target}_breached_at"
    due_column = "response_due_at" if target == "response" else "resolve_due_at"
    with transaction.atomic():
        updated = Incident.objects.filter(
            pk=incident_id, status__in=ACTIVE_STATUSES, **{f"{column}__isnull": True}
        ).update(**{column: now, "sla_status": SLAStatus.BREACHED, "updated_at": now})
        if not updated:
            return False
        incident = Incident.objects.get(pk=incident_id)
        record_system_event(
            incident,
            EventType.SLA_BREACHED,
            target=target,
            due_at=getattr(incident, due_column).isoformat(),
        )
    logger.warning("SLA breached", extra={"incident_id": incident_id, "target": target})
    return True


def check_sla(now=None) -> SLARunResult:
    now = now or timezone.now()
    result = SLARunResult()
    active = Incident.objects.filter(status__in=ACTIVE_STATUSES)

    response_ids = active.filter(
        acknowledged_at__isnull=True,
        response_due_at__lt=now,
        response_breached_at__isnull=True,
    ).values_list("pk", flat=True)
    for pk in response_ids:
        if _flag_breach(pk, "response", now):
            result.response_breaches.append(pk)

    resolution_ids = active.filter(
        resolve_due_at__lt=now, resolution_breached_at__isnull=True
    ).values_list("pk", flat=True)
    for pk in resolution_ids:
        if _flag_breach(pk, "resolution", now):
            result.resolution_breaches.append(pk)

    # At risk: most of the resolution window used, not breached yet. Status only, no event.
    result.at_risk = (
        active.filter(sla_status=SLAStatus.OK, resolve_due_at__isnull=False)
        .filter(
            resolve_due_at__lte=now
            + (F("resolve_due_at") - F("created_at")) * (1 - AT_RISK_FRACTION)
        )
        .update(sla_status=SLAStatus.AT_RISK)
    )
    return result


def send_reminders(now=None) -> list[int]:
    """Remind about unresolved incidents whose priority has a reminder interval.

    At most one reminder per incident per interval, however many workers run this.
    """
    now = now or timezone.now()
    reminded = []
    for policy in SLAPolicy.objects.filter(reminder_interval_minutes__isnull=False):
        interval = timedelta(minutes=policy.reminder_interval_minutes)
        cutoff = now - interval
        due = Incident.objects.filter(status__in=ACTIVE_STATUSES, priority=policy.priority).filter(
            Q(last_reminded_at__lte=cutoff)
            | Q(last_reminded_at__isnull=True, created_at__lte=cutoff)
        )
        for pk in due.values_list("pk", flat=True):
            with transaction.atomic():
                # Claim: only the run that moves last_reminded_at sends the reminder.
                claimed = (
                    Incident.objects.filter(pk=pk)
                    .filter(
                        Q(last_reminded_at__lte=cutoff)
                        | Q(last_reminded_at__isnull=True, created_at__lte=cutoff)
                    )
                    .update(last_reminded_at=now)
                )
                if not claimed:
                    continue
                incident = Incident.objects.get(pk=pk)
                record_system_event(
                    incident,
                    EventType.REMINDER_SENT,
                    interval_minutes=policy.reminder_interval_minutes,
                    window_start=now.isoformat(),
                )
            reminded.append(pk)
    if reminded:
        logger.info("reminders sent", extra={"incident_ids": reminded})
    return reminded
