"""Query-parameter filtering for the incident list. Bad parameters give 400, not silence."""

from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from rest_framework import serializers

from .models import PRIORITY_RANK, Incident, Priority, SLAStatus, Status

ORDERING = {
    "created_at": ("created_at",),
    "-created_at": ("-created_at",),
    "updated_at": ("updated_at",),
    "-updated_at": ("-updated_at",),
    "priority": ("priority_rank", "-created_at"),  # most urgent first
    "-priority": ("-priority_rank", "-created_at"),
    "resolve_due_at": ("resolve_due_at", "-created_at"),
    "-resolve_due_at": ("-resolve_due_at", "-created_at"),
}


class CommaSeparatedChoices(serializers.CharField):
    """`?status=open,in_progress` -> ["open", "in_progress"], each value validated."""

    def __init__(self, choices, **kwargs):
        self.allowed = set(choices)
        kwargs.setdefault("help_text", f"Comma-separated: {', '.join(choices)}")
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        values = [v.strip() for v in data.split(",") if v.strip()]
        bad = [v for v in values if v not in self.allowed]
        if bad:
            raise serializers.ValidationError(
                f"Invalid value(s): {', '.join(bad)}. Allowed: {', '.join(sorted(self.allowed))}."
            )
        return values


class IncidentFilterSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, max_length=200)
    status = CommaSeparatedChoices(Status.values, required=False)
    priority = CommaSeparatedChoices(Priority.values, required=False)
    sla_status = CommaSeparatedChoices(SLAStatus.values, required=False)
    assignee = serializers.CharField(required=False, help_text="User id, 'me' or 'none'.")
    reporter = serializers.IntegerField(required=False, min_value=1)
    created_after = serializers.DateTimeField(required=False)
    created_before = serializers.DateTimeField(required=False)
    ordering = serializers.ChoiceField(choices=list(ORDERING), required=False)

    def validate_assignee(self, value):
        if value in ("me", "none"):
            return value
        if not value.isdigit():
            raise serializers.ValidationError("Must be a user id, 'me' or 'none'.")
        return int(value)


def with_priority_rank(qs: QuerySet) -> QuerySet:
    return qs.annotate(
        priority_rank=Case(
            *[When(priority=p, then=Value(rank)) for p, rank in PRIORITY_RANK.items()],
            output_field=IntegerField(),
        )
    )


def filter_incidents(qs: QuerySet[Incident], params, user) -> QuerySet[Incident]:
    f = IncidentFilterSerializer(data=params)
    f.is_valid(raise_exception=True)
    data = f.validated_data

    if term := data.get("search"):
        qs = qs.filter(
            Q(title__icontains=term) | Q(description__icontains=term) | Q(reference__iexact=term)
        )
    if values := data.get("status"):
        qs = qs.filter(status__in=values)
    if values := data.get("priority"):
        qs = qs.filter(priority__in=values)
    if values := data.get("sla_status"):
        qs = qs.filter(sla_status__in=values)
    if (assignee := data.get("assignee")) is not None:
        if assignee == "me":
            qs = qs.filter(assignee=user)
        elif assignee == "none":
            qs = qs.filter(assignee__isnull=True)
        else:
            qs = qs.filter(assignee_id=assignee)
    if reporter := data.get("reporter"):
        qs = qs.filter(reporter_id=reporter)
    if after := data.get("created_after"):
        qs = qs.filter(created_at__gte=after)
    if before := data.get("created_before"):
        qs = qs.filter(created_at__lt=before)

    qs = with_priority_rank(qs)
    return qs.order_by(*ORDERING[data.get("ordering", "-created_at")])
