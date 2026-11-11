from django.conf import settings
from django.db import models


class Kind(models.TextChoices):
    INCIDENT_CREATED = "incident_created", "Incident created"
    INCIDENT_ASSIGNED = "incident_assigned", "Incident assigned"
    PRIORITY_CHANGED = "priority_changed", "Priority changed"
    SLA_BREACHED = "sla_breached", "SLA breached"
    REMINDER = "reminder", "Reminder"


class Channel(models.TextChoices):
    IN_APP = "in_app", "In-app"
    EMAIL = "email", "Email"


class Notification(models.Model):
    """What a user sees in the app's notification list."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    incident = models.ForeignKey(
        "incidents.Incident", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "read_at"])]

    def __str__(self) -> str:
        return f"{self.kind} for {self.recipient_id}"


class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


FINAL_STATUSES = (DeliveryStatus.SENT, DeliveryStatus.FAILED, DeliveryStatus.SKIPPED)


class NotificationDelivery(models.Model):
    """One message to one person on one channel. `dedupe_key` makes it happen at most once."""

    dedupe_key = models.CharField(max_length=255, unique=True)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    incident = models.ForeignKey(
        "incidents.Incident", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    channel = models.CharField(max_length=16, choices=Channel.choices)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(
        max_length=16, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    notification = models.ForeignKey(
        Notification, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]
        verbose_name_plural = "notification deliveries"

    def __str__(self) -> str:
        return self.dedupe_key
