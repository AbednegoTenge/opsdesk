"""Report generation runs on the `reports` queue, never in the API request."""

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.notifications.models import Channel, Kind, NotificationDelivery
from apps.notifications.tasks import deliver_notification
from apps.users.models import Role, User
from opsdesk_tasks.base import OpsDeskTask

from . import services
from .models import IncidentReport, ReportKind, ReportStatus

logger = logging.getLogger(__name__)


class ReportTask(OpsDeskTask):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        super().on_failure(exc, task_id, args, kwargs, einfo)
        report_id = kwargs.get("report_id") or (args[0] if args else None)
        IncidentReport.objects.filter(pk=report_id, status=ReportStatus.PENDING).update(
            status=ReportStatus.FAILED, error=repr(exc)[:2000]
        )


@shared_task(name="reporting.generate_report", base=ReportTask, soft_time_limit=240, time_limit=300)
def generate_report(report_id: int) -> str:
    with transaction.atomic():
        report = (
            IncidentReport.objects.select_for_update(skip_locked=True).filter(pk=report_id).first()
        )
        if report is None:
            # Missing, or another worker holds the lock and is generating it.
            return "skipped"
        if report.status == ReportStatus.COMPLETED:
            return "already_completed"
        report.data = services.build_report_data(report.period_start, report.period_end)
        report.status = ReportStatus.COMPLETED
        report.error = ""
        report.completed_at = timezone.now()
        report.save(update_fields=["data", "status", "error", "completed_at"])

        delivery_ids = []
        if report.kind in (ReportKind.DAILY, ReportKind.WEEKLY):
            delivery_ids = _queue_admin_emails(report)
        transaction.on_commit(lambda: [deliver_notification.delay(pk) for pk in delivery_ids])

    logger.info("report generated", extra={"report_id": report_id, "kind": report.kind})
    return "completed"


def _queue_admin_emails(report: IncidentReport) -> list[int]:
    subject = (
        f"[OpsDesk] {report.get_kind_display()} incident report {report.period_start:%Y-%m-%d}"
    )
    body = services.summary_text(report)
    ids = []
    for admin in User.objects.filter(role=Role.ADMIN, is_active=True):
        delivery, _ = NotificationDelivery.objects.get_or_create(
            dedupe_key=f"report:{report.pk}:user:{admin.pk}:{Channel.EMAIL}",
            defaults={
                "recipient": admin,
                "kind": Kind.REPORT,
                "channel": Channel.EMAIL,
                "subject": subject,
                "body": body,
            },
        )
        ids.append(delivery.pk)
    return ids


@shared_task(name="reporting.schedule_periodic_report", base=OpsDeskTask)
def schedule_periodic_report(kind: str) -> dict:
    """Beat entry point: create (once) and queue the report for the last complete period."""
    start, end = services.previous_period(kind)
    report, created = services.request_report(kind, start, end)
    return {"report_id": report.pk, "created": created}
