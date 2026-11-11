from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from kombu.exceptions import OperationalError as BrokerError

from apps.incidents import services
from apps.users.models import Role
from opsdesk_tasks import outbox
from opsdesk_tasks.models import OutboxMessage, OutboxStatus
from opsdesk_tasks.tasks import dispatch_pending_outbox

from ..factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def broker_down(monkeypatch):
    def fail(*args, **kwargs):
        raise BrokerError("Error 111 connecting to redis:6379. Connection refused.")

    monkeypatch.setattr("celery.canvas.Signature.apply_async", fail)


def age(message, seconds):
    OutboxMessage.objects.filter(pk=message.pk).update(
        created_at=timezone.now() - timedelta(seconds=seconds)
    )


def test_broker_outage_keeps_the_task_and_does_not_break_the_request(
    broker_down, client_for, django_capture_on_commit_callbacks
):
    admin = UserFactory(role=Role.ADMIN)
    with django_capture_on_commit_callbacks(execute=True):
        res = client_for(UserFactory(role=Role.ENGINEER)).post(
            "/api/v1/incidents/", {"title": "x"}, format="json"
        )
    assert res.status_code == 201  # the incident is saved even though Redis is down
    message = OutboxMessage.objects.get()
    assert message.status == OutboxStatus.PENDING
    assert message.attempts == 1
    assert "Connection refused" in message.last_error
    assert not mail.outbox
    assert admin  # notified later by the sweep (next test)


def test_sweep_publishes_rows_that_missed_their_publish(
    broker_down, monkeypatch, django_capture_on_commit_callbacks
):
    admin = UserFactory(role=Role.ADMIN, email="boss@example.com")
    with django_capture_on_commit_callbacks(execute=True):
        services.create_incident(actor=UserFactory(role=Role.ENGINEER), title="x")
    message = OutboxMessage.objects.get()
    age(message, 120)

    monkeypatch.undo()  # Redis is back
    assert dispatch_pending_outbox.apply().get() == 1
    message.refresh_from_db()
    assert message.status == OutboxStatus.SENT
    assert message.dispatched_at is not None
    assert [m.to for m in mail.outbox] == [[admin.email]]


def test_sweep_leaves_fresh_rows_for_their_own_publish(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False):
        services.create_incident(actor=UserFactory(role=Role.ENGINEER), title="x")
    assert outbox.dispatch_pending() == 0
    assert OutboxMessage.objects.get().status == OutboxStatus.PENDING


def test_sent_rows_are_not_published_again(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        services.create_incident(actor=UserFactory(role=Role.ENGINEER), title="x")
    message = OutboxMessage.objects.get()
    age(message, 120)
    assert outbox.publish(message.pk) is False
    assert outbox.dispatch_pending() == 0
