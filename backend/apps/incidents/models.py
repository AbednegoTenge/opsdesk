from django.conf import settings
from django.db import models


class Priority(models.TextChoices):
    CRITICAL = "critical", "Critical"
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


# Lower number = more urgent. Used for ordering.
PRIORITY_RANK = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.MEDIUM: 2, Priority.LOW: 3}


class Status(models.TextChoices):
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In Progress"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


ACTIVE_STATUSES = (Status.OPEN, Status.IN_PROGRESS)


class SLAStatus(models.TextChoices):
    OK = "ok", "OK"
    AT_RISK = "at_risk", "At risk"
    BREACHED = "breached", "Breached"


class SLAPolicy(models.Model):
    """Response and resolution targets per priority. One row per priority."""

    priority = models.CharField(max_length=16, choices=Priority.choices, primary_key=True)
    response_minutes = models.PositiveIntegerField()
    resolution_minutes = models.PositiveIntegerField()
    reminder_interval_minutes = models.PositiveIntegerField(
        null=True, blank=True, help_text="Reminder cadence for unresolved incidents; empty = none."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "SLA policies"

    def __str__(self) -> str:
        return (
            f"{self.priority}: respond {self.response_minutes}m, resolve {self.resolution_minutes}m"
        )


class Incident(models.Model):
    # NULL (not "") until the row has a pk, so concurrent inserts do not clash on UNIQUE.
    reference = models.CharField(max_length=20, unique=True, null=True, editable=False)  # noqa: DJ001
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    sla_status = models.CharField(max_length=16, choices=SLAStatus.choices, default=SLAStatus.OK)

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reported_incidents"
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_incidents",
    )

    response_due_at = models.DateTimeField(null=True, blank=True)
    resolve_due_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    last_reminded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["assignee", "status"]),
            models.Index(fields=["sla_status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference or 'INC-?'} {self.title}"

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


class Comment(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="incident_comments"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["incident", "created_at"])]

    def __str__(self) -> str:
        return f"Comment {self.pk} on incident {self.incident_id}"


class EventType(models.TextChoices):
    CREATED = "created", "Created"
    UPDATED = "updated", "Updated"
    PRIORITY_CHANGED = "priority_changed", "Priority changed"
    ASSIGNED = "assigned", "Assigned"
    UNASSIGNED = "unassigned", "Unassigned"
    STATUS_CHANGED = "status_changed", "Status changed"
    COMMENT_ADDED = "comment_added", "Comment added"
    COMMENT_EDITED = "comment_edited", "Comment edited"
    COMMENT_DELETED = "comment_deleted", "Comment deleted"
    SLA_BREACHED = "sla_breached", "SLA breached"
    REMINDER_SENT = "reminder_sent", "Reminder sent"


class AppendOnlyError(RuntimeError):
    pass


class IncidentEvent(models.Model):
    """Append-only activity history. Written in the same transaction as the change."""

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Empty for system events (SLA monitor, reminders).",
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["incident", "created_at"])]

    def __str__(self) -> str:
        return f"{self.event_type} on incident {self.incident_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise AppendOnlyError("IncidentEvent rows cannot be modified.")
        super().save(*args, **kwargs)
