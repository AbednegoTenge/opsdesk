from django.conf import settings
from django.db import models


class ReportKind(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    ADHOC = "adhoc", "On demand"


class ReportStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class IncidentReport(models.Model):
    """A summary of incident activity over [period_start, period_end).

    One row per (kind, period): asking for the same report twice returns the same row.
    """

    kind = models.CharField(max_length=16, choices=ReportKind.choices)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    status = models.CharField(
        max_length=16, choices=ReportStatus.choices, default=ReportStatus.PENDING
    )
    data = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period_start", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "period_start", "period_end"], name="unique_report_period"
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gt=models.F("period_start")),
                name="report_period_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} report {self.period_start:%Y-%m-%d}..{self.period_end:%Y-%m-%d}"
