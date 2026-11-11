from celery import shared_task

from opsdesk_tasks.base import OpsDeskTask

from . import services


@shared_task(name="sla.check_breaches", base=OpsDeskTask, soft_time_limit=50, time_limit=60)
def check_breaches() -> dict:
    result = services.check_sla()
    return {
        "response_breaches": len(result.response_breaches),
        "resolution_breaches": len(result.resolution_breaches),
        "at_risk": result.at_risk,
    }


@shared_task(name="sla.send_reminders", base=OpsDeskTask, soft_time_limit=240, time_limit=280)
def send_reminders() -> int:
    return len(services.send_reminders())
