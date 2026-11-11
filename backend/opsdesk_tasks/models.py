from django.db import models


class OutboxStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SENT = "sent", "Sent"


class OutboxMessage(models.Model):
    """A task to publish, written in the same transaction as the change that caused it.

    If the broker is unreachable when the transaction commits, the row stays pending and
    the periodic sweep publishes it later, so no task is lost.
    """

    task_name = models.CharField(max_length=200)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16, choices=OutboxStatus.choices, default=OutboxStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return f"{self.task_name} #{self.pk} ({self.status})"
