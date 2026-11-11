"""Dashboard figures. Each function is a fixed, small number of aggregate queries,
however many incidents exist."""

from datetime import UTC, datetime, time, timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.incidents.models import (
    ACTIVE_STATUSES,
    EventType,
    Incident,
    IncidentEvent,
    Priority,
    SLAStatus,
    Status,
)
from apps.users.models import Role, User

ACTIVE = Q(status__in=ACTIVE_STATUSES)


def summary() -> dict:
    counts = Incident.objects.aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(status=Status.OPEN)),
        in_progress=Count("id", filter=Q(status=Status.IN_PROGRESS)),
        resolved=Count("id", filter=Q(status=Status.RESOLVED)),
        closed=Count("id", filter=Q(status=Status.CLOSED)),
        critical_total=Count("id", filter=Q(priority=Priority.CRITICAL)),
        critical_active=Count("id", filter=ACTIVE & Q(priority=Priority.CRITICAL)),
        unassigned_active=Count("id", filter=ACTIVE & Q(assignee__isnull=True)),
        sla_breached_active=Count("id", filter=ACTIVE & Q(sla_status=SLAStatus.BREACHED)),
        sla_at_risk_active=Count("id", filter=ACTIVE & Q(sla_status=SLAStatus.AT_RISK)),
        **{f"active_{p}": Count("id", filter=ACTIVE & Q(priority=p)) for p in Priority.values},
    )
    return {
        "total": counts["total"],
        "active": counts["open"] + counts["in_progress"],
        "by_status": {s: counts[s] for s in Status.values},
        "active_by_priority": {p: counts[f"active_{p}"] for p in Priority.values},
        "critical": {"total": counts["critical_total"], "active": counts["critical_active"]},
        "unassigned_active": counts["unassigned_active"],
        "sla": {
            "breached_active": counts["sla_breached_active"],
            "at_risk_active": counts["sla_at_risk_active"],
        },
    }


def by_assignee(days: int = 30) -> dict:
    since = timezone.now() - timedelta(days=days)
    rows = (
        User.objects.filter(is_active=True, role__in=[Role.ENGINEER, Role.ADMIN])
        .annotate(
            active=Count(
                "assigned_incidents", filter=Q(assigned_incidents__status__in=ACTIVE_STATUSES)
            ),
            in_progress=Count(
                "assigned_incidents", filter=Q(assigned_incidents__status=Status.IN_PROGRESS)
            ),
            critical_active=Count(
                "assigned_incidents",
                filter=Q(
                    assigned_incidents__status__in=ACTIVE_STATUSES,
                    assigned_incidents__priority=Priority.CRITICAL,
                ),
            ),
            breached_active=Count(
                "assigned_incidents",
                filter=Q(
                    assigned_incidents__status__in=ACTIVE_STATUSES,
                    assigned_incidents__sla_status=SLAStatus.BREACHED,
                ),
            ),
            resolved_recent=Count(
                "assigned_incidents", filter=Q(assigned_incidents__resolved_at__gte=since)
            ),
        )
        .order_by("-active", "email")
        .values(
            "id",
            "email",
            "full_name",
            "role",
            "active",
            "in_progress",
            "critical_active",
            "breached_active",
            "resolved_recent",
        )
    )
    unassigned = Incident.objects.filter(ACTIVE, assignee__isnull=True).count()
    return {"resolved_window_days": days, "engineers": list(rows), "unassigned_active": unassigned}


def trends(days: int = 30) -> dict:
    """Daily created / resolved / SLA-breach counts for the last `days` days (UTC), oldest first."""
    today = timezone.now().astimezone(UTC).date()
    first_day = today - timedelta(days=days - 1)
    start = datetime.combine(first_day, time.min, tzinfo=UTC)

    def per_day(qs, field):
        return dict(
            qs.annotate(day=TruncDate(field, tzinfo=UTC))
            .values("day")
            .annotate(n=Count("id"))
            .values_list("day", "n")
        )

    created = per_day(Incident.objects.filter(created_at__gte=start), "created_at")
    resolved = per_day(Incident.objects.filter(resolved_at__gte=start), "resolved_at")
    breaches = per_day(
        IncidentEvent.objects.filter(event_type=EventType.SLA_BREACHED, created_at__gte=start),
        "created_at",
    )
    mttr = Incident.objects.filter(resolved_at__gte=start).aggregate(
        v=Avg(ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField()))
    )["v"]

    series = []
    for i in range(days):
        day = first_day + timedelta(days=i)
        series.append(
            {
                "date": day.isoformat(),
                "created": created.get(day, 0),
                "resolved": resolved.get(day, 0),
                "sla_breaches": breaches.get(day, 0),
            }
        )
    return {
        "days": days,
        "series": series,
        "totals": {
            "created": sum(r["created"] for r in series),
            "resolved": sum(r["resolved"] for r in series),
            "sla_breaches": sum(r["sla_breaches"] for r in series),
        },
        "mean_time_to_resolve_seconds": None if mttr is None else round(mttr.total_seconds(), 1),
    }
