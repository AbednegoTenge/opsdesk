from celery import shared_task

from . import outbox
from .base import OpsDeskTask


@shared_task(name="outbox.dispatch_pending", base=OpsDeskTask)
def dispatch_pending_outbox() -> int:
    return outbox.dispatch_pending()
