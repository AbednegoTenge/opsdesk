# Load the Celery app when Django starts so tasks sent from the API use its configuration.
from .celery import app as celery_app

__all__ = ("celery_app",)
