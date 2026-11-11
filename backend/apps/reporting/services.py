"""Report periods, report requests and the statistics a report contains."""

from datetime import UTC, datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.utils import timezone

from apps.incidents.models import (
    ACTIVE_STATUSES,
    EventType,
    Incident,
    IncidentEvent,
    Priority,
    Status,
)
from opsdesk_tasks import outbox

from .models import IncidentReport, ReportKind


def previous_period(kind: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    """The last complete day (UTC) or the last complete Monday-to-Monday week."""
    now = (now or timezone.now()).astimezone(UTC)
    today = datetime.combine(now.date(), time.min, tzinfo=UTC)
    if kind == ReportKind.DAILY:
        return today - timedelta(days=1), today
    if kind == ReportKind.WEEKLY:
        this_monday = today - timedelta(days=today.weekday())
        return this_monday - timedelta(days=7), this_monday
    raise ValueError(f"no automatic period for {kind!r}")


def request_report(kind: str, start: datetime, end: datetime, requested_by=None):
    """Get or create the report for a period and queue generation after commit.

    Returns (report, created). An existing completed report is returned as is.
    """
    with transaction.atomic():
        try:
            with transaction.atomic():
                report = IncidentReport.objects.create(
                    kind=kind, period_start=start, period_end=end, requested_by=requested_by
                )
            created = True
        except IntegrityError:
            report = IncidentReport.objects.get(kind=kind, period_start=start, period_end=end)
            created = False
        if created:
            outbox.enqueue("reporting.generate_report", report_id=report.pk)
    return report, created


def _seconds(value) -> float | None:
    return None if value is None else round(value.total_seconds(), 1)


def build_report_data(start: datetime, end: datetime) -> dict:
    created = Incident.objects.filter(created_at__gte=start, created_at__lt=end)
    resolved = Incident.objects.filter(resolved_at__gte=start, resolved_at__lt=end)
    breaches = IncidentEvent.objects.filter(
        event_type=EventType.SLA_BREACHED, created_at__gte=start, created_at__lt=end
    )

    by_priority = dict(created.values_list("priority").annotate(n=Count("id")))
    mttr = resolved.aggregate(
        v=Avg(ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField()))
    )["v"]
    mtta = created.filter(acknowledged_at__isnull=False).aggregate(
        v=Avg(
            ExpressionWrapper(F("acknowledged_at") - F("created_at"), output_field=DurationField())
        )
    )["v"]

    per_engineer = (
        Incident.objects.filter(assignee__isnull=False)
        .values("assignee_id", "assignee__email", "assignee__full_name")
        .annotate(
            open=Count("id", filter=Q(status__in=ACTIVE_STATUSES)),
            resolved_in_period=Count("id", filter=Q(resolved_at__gte=start, resolved_at__lt=end)),
        )
        .filter(Q(open__gt=0) | Q(resolved_in_period__gt=0))
        .order_by("-open", "assignee__email")
    )

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "created": created.count(),
        "resolved": resolved.count(),
        "created_by_priority": {p: by_priority.get(p, 0) for p in Priority.values},
        "sla_breaches": {
            "total": breaches.count(),
            "response": breaches.filter(data__target="response").count(),
            "resolution": breaches.filter(data__target="resolution").count(),
        },
        "mean_time_to_resolve_seconds": _seconds(mttr),
        "mean_time_to_acknowledge_seconds": _seconds(mtta),
        # Snapshot at generation time, not at period end.
        "open_now": Incident.objects.filter(status__in=ACTIVE_STATUSES).count(),
        "open_critical_now": Incident.objects.filter(
            status__in=ACTIVE_STATUSES, priority=Priority.CRITICAL
        ).count(),
        "status_now": {s: Incident.objects.filter(status=s).count() for s in Status.values},
        "per_engineer": [
            {
                "user_id": row["assignee_id"],
                "email": row["assignee__email"],
                "name": row["assignee__full_name"],
                "open": row["open"],
                "resolved_in_period": row["resolved_in_period"],
            }
            for row in per_engineer
        ],
    }


def summary_text(report: IncidentReport) -> str:
    d = report.data
    lines = [
        f"OpsDesk {report.get_kind_display().lower()} report",
        f"{report.period_start:%Y-%m-%d %H:%M} to {report.period_end:%Y-%m-%d %H:%M} UTC",
        "",
        f"Created: {d['created']}   Resolved: {d['resolved']}",
        f"SLA breaches: {d['sla_breaches']['total']}",
        f"Open now: {d['open_now']} ({d['open_critical_now']} critical)",
    ]
    if d["mean_time_to_resolve_seconds"] is not None:
        lines.append(f"Mean time to resolve: {d['mean_time_to_resolve_seconds'] / 3600:.1f} h")
    return "\n".join(lines)
