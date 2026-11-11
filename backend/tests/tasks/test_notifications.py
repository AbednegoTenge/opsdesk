"""Notification tasks: enqueue-after-commit, fan-out, retries, failure, and duplicate protection."""

import logging

import pytest
from django.core import mail
from django.db import DatabaseError, transaction
from django.test import override_settings

from apps.incidents import services
from apps.incidents.models import EventType, IncidentEvent
from apps.notifications import channels, tasks
from apps.notifications.models import DeliveryStatus, Notification, NotificationDelivery
from apps.users.models import Role
from opsdesk_tasks.models import OutboxMessage, OutboxStatus

from ..factories import IncidentFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def people(db):
    return {
        "admin": UserFactory(role=Role.ADMIN, email="boss@example.com"),
        "reporter": UserFactory(role=Role.ENGINEER, email="rep@example.com"),
        "oncall": UserFactory(role=Role.ENGINEER, email="oncall@example.com"),
    }


def emails_to(address):
    return [m for m in mail.outbox if address in m.to]


# --- enqueue only after commit -------------------------------------------------
class TestEnqueueAfterCommit:
    def test_nothing_is_published_before_commit(self, people, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            services.create_incident(actor=people["reporter"], title="DB down")
        # The outbox row exists in the transaction, but no task ran yet.
        assert OutboxMessage.objects.filter(status=OutboxStatus.PENDING).count() == 1
        assert NotificationDelivery.objects.count() == 0
        assert len(callbacks) == 1

    def test_published_and_delivered_after_commit(self, people, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            incident = services.create_incident(actor=people["reporter"], title="DB down")
        assert OutboxMessage.objects.get().status == OutboxStatus.SENT
        assert len(emails_to("boss@example.com")) == 1
        assert Notification.objects.get(recipient=people["admin"]).incident == incident

    def test_rolled_back_change_publishes_nothing(self, people, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            with pytest.raises(RuntimeError), transaction.atomic():
                services.create_incident(actor=people["reporter"], title="never happened")
                raise RuntimeError("request failed after the write")
        assert callbacks == []
        assert OutboxMessage.objects.count() == 0
        assert mail.outbox == []

    @pytest.mark.django_db(transaction=True)
    def test_enqueue_outside_transaction_is_a_bug(self):
        from opsdesk_tasks import outbox

        with pytest.raises(RuntimeError):
            outbox.enqueue("notifications.notify_incident_event", event_id=1)


# --- who gets notified ----------------------------------------------------------------
class TestRecipients:
    def test_new_incident_notifies_admins_but_not_the_reporter(
        self, people, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            services.create_incident(actor=people["reporter"], title="x")
        assert emails_to("boss@example.com")
        assert not emails_to("rep@example.com")

    def test_assignment_notifies_new_assignee_once(
        self, people, django_capture_on_commit_callbacks
    ):
        incident = IncidentFactory(reporter=people["reporter"])
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            services.assign_incident(
                incident_id=incident.pk, actor=people["admin"], assignee=people["oncall"]
            )
        sent = emails_to("oncall@example.com")
        assert len(sent) == 1
        assert "assigned to you" in sent[0].subject
        assert Notification.objects.filter(recipient=people["oncall"]).count() == 1

    def test_reassignment_notifies_the_new_assignee(
        self, people, django_capture_on_commit_callbacks
    ):
        other = UserFactory(role=Role.ENGINEER, email="other@example.com")
        incident = IncidentFactory(assignee=people["oncall"])
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            services.assign_incident(incident_id=incident.pk, actor=people["admin"], assignee=other)
        assert emails_to("other@example.com")
        assert not emails_to("oncall@example.com")

    def test_self_assignment_sends_nothing(self, people, django_capture_on_commit_callbacks):
        incident = IncidentFactory()
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            services.assign_incident(
                incident_id=incident.pk, actor=people["oncall"], assignee=people["oncall"]
            )
        assert mail.outbox == []

    def test_priority_change_notifies_assignee_and_reporter(
        self, people, django_capture_on_commit_callbacks
    ):
        incident = IncidentFactory(reporter=people["reporter"], assignee=people["oncall"])
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            services.update_incident(
                incident_id=incident.pk, actor=people["admin"], priority="critical"
            )
        assert len(emails_to("oncall@example.com")) == 1
        assert len(emails_to("rep@example.com")) == 1
        assert "critical" in emails_to("rep@example.com")[0].subject

    def test_title_edit_notifies_nobody(self, people, django_capture_on_commit_callbacks):
        incident = IncidentFactory(assignee=people["oncall"])
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            services.update_incident(incident_id=incident.pk, actor=people["admin"], title="new")
        assert mail.outbox == []

    def test_through_the_api(self, people, client_for, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            res = client_for(people["reporter"]).post(
                "/api/v1/incidents/",
                {
                    "title": "Checkout failing",
                    "priority": "critical",
                    "assignee_id": people["oncall"].pk,
                },
                format="json",
            )
        assert res.status_code == 201
        assert len(emails_to("boss@example.com")) == 1
        assert len(emails_to("oncall@example.com")) == 1


# --- duplicate protection --------------------------------------------------------------------
class TestDuplicates:
    def _assigned_event(self, people):
        incident = IncidentFactory()
        services.assign_incident(
            incident_id=incident.pk, actor=people["admin"], assignee=people["oncall"]
        )
        return IncidentEvent.objects.get(incident=incident, event_type=EventType.ASSIGNED)

    def test_fan_out_twice_sends_once(self, people):
        event = self._assigned_event(people)
        mail.outbox.clear()
        tasks.notify_incident_event.apply(kwargs={"event_id": event.pk}, throw=True)
        tasks.notify_incident_event.apply(kwargs={"event_id": event.pk}, throw=True)
        assert (
            NotificationDelivery.objects.filter(recipient=people["oncall"]).count() == 2
        )  # 2 channels
        assert len(emails_to("oncall@example.com")) == 1
        assert Notification.objects.filter(recipient=people["oncall"]).count() == 1

    def test_redelivered_send_is_skipped(self, people):
        event = self._assigned_event(people)
        tasks.notify_incident_event.apply(kwargs={"event_id": event.pk}, throw=True)
        delivery = NotificationDelivery.objects.get(recipient=people["oncall"], channel="email")
        result = tasks.deliver_notification.apply(kwargs={"delivery_id": delivery.pk}, throw=True)
        assert result.get() == "duplicate"
        assert len(emails_to("oncall@example.com")) == 1

    def test_row_locked_by_another_worker_is_left_alone(self, people, monkeypatch):
        event = self._assigned_event(people)
        monkeypatch.setattr(tasks.deliver_notification, "delay", lambda pk: None)
        tasks.notify_incident_event.apply(kwargs={"event_id": event.pk}, throw=True)
        delivery = NotificationDelivery.objects.get(recipient=people["oncall"], channel="email")

        def locked(*a, **k):
            raise DatabaseError("could not obtain lock on row in relation")

        monkeypatch.setattr(NotificationDelivery.objects, "select_for_update", locked)
        result = tasks.deliver_notification.apply(kwargs={"delivery_id": delivery.pk}, throw=True)
        assert result.get() == "busy"
        assert mail.outbox == []

    def test_pending_rows_from_a_crashed_run_are_resent(self, people, monkeypatch):
        event = self._assigned_event(people)
        # First run "crashes" after creating rows but before sending.
        monkeypatch.setattr(tasks.deliver_notification, "delay", lambda pk: None)
        tasks.notify_incident_event.apply(kwargs={"event_id": event.pk}, throw=True)
        assert mail.outbox == []
        monkeypatch.undo()
        tasks.notify_incident_event.apply(kwargs={"event_id": event.pk}, throw=True)
        assert len(emails_to("oncall@example.com")) == 1

    def test_deleted_incident_is_ignored(self, people):
        event = self._assigned_event(people)
        event_id = event.pk
        event.incident.delete()
        assert tasks.notify_incident_event.apply(kwargs={"event_id": event_id}).get() == {
            "status": "missing"
        }


# --- retries and failures -----------------------------------------------------------
@pytest.fixture
def email_delivery(people, monkeypatch):
    incident = IncidentFactory()
    services.assign_incident(
        incident_id=incident.pk, actor=people["admin"], assignee=people["oncall"]
    )
    event = IncidentEvent.objects.get(incident=incident, event_type=EventType.ASSIGNED)
    monkeypatch.setattr(tasks.deliver_notification, "delay", lambda pk: None)
    tasks.notify_incident_event.apply(kwargs={"event_id": event.pk}, throw=True)
    monkeypatch.undo()
    mail.outbox.clear()
    return NotificationDelivery.objects.get(recipient=people["oncall"], channel="email")


SMTP_DOWN = ConnectionError("smtp unreachable")


def flaky_email(monkeypatch, failures, exc=SMTP_DOWN):
    calls = {"n": 0}
    real = channels.send_email

    def send(delivery):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise exc
        return real(delivery)

    monkeypatch.setitem(channels.SENDERS, "email", send)
    return calls


class TestRetries:
    def test_transient_failure_is_retried_then_sent(self, email_delivery, monkeypatch):
        calls = flaky_email(monkeypatch, failures=2)
        result = tasks.deliver_notification.apply(kwargs={"delivery_id": email_delivery.pk})
        assert result.get() == "sent"
        email_delivery.refresh_from_db()
        assert email_delivery.status == DeliveryStatus.SENT
        assert email_delivery.attempts == 3
        assert calls["n"] == 3
        assert len(mail.outbox) == 1

    @override_settings(TASK_MAX_RETRIES=2)
    def test_gives_up_after_max_retries_and_marks_failed(self, email_delivery, monkeypatch):
        calls = flaky_email(monkeypatch, failures=99)
        result = tasks.deliver_notification.apply(kwargs={"delivery_id": email_delivery.pk})
        assert result.failed()
        email_delivery.refresh_from_db()
        assert email_delivery.status == DeliveryStatus.FAILED
        assert email_delivery.attempts == 3  # first try + 2 retries
        assert "smtp unreachable" in email_delivery.last_error
        assert calls["n"] == 3
        assert mail.outbox == []

    def test_permanent_error_is_not_retried(self, email_delivery, monkeypatch):
        calls = flaky_email(
            monkeypatch, 99, channels.PermanentDeliveryError("mailbox does not exist")
        )
        assert (
            tasks.deliver_notification.apply(kwargs={"delivery_id": email_delivery.pk}).get()
            == "failed"
        )
        email_delivery.refresh_from_db()
        assert email_delivery.status == DeliveryStatus.FAILED
        assert email_delivery.attempts == 1
        assert calls["n"] == 1

    def test_unexpected_bug_fails_fast(self, email_delivery, monkeypatch):
        calls = flaky_email(monkeypatch, 99, ValueError("template bug"))
        result = tasks.deliver_notification.apply(kwargs={"delivery_id": email_delivery.pk})
        assert result.failed()
        assert calls["n"] == 1
        email_delivery.refresh_from_db()
        assert email_delivery.status == DeliveryStatus.FAILED

    def test_inactive_recipient_is_skipped(self, email_delivery, people):
        people["oncall"].is_active = False
        people["oncall"].save()
        assert (
            tasks.deliver_notification.apply(kwargs={"delivery_id": email_delivery.pk}).get()
            == "skipped"
        )
        assert mail.outbox == []

    def test_retry_policy(self):
        task = tasks.deliver_notification
        assert task.acks_late is True
        assert task.retry_jitter is True
        assert task.retry_backoff == 2
        assert ConnectionError in task.autoretry_for

    @override_settings(TASK_MAX_RETRIES=1)
    def test_failures_and_retries_are_logged(self, email_delivery, monkeypatch, caplog):
        flaky_email(monkeypatch, failures=99)
        with caplog.at_level(logging.INFO, logger="opsdesk.tasks"):
            tasks.deliver_notification.apply(kwargs={"delivery_id": email_delivery.pk})
        messages = [r.getMessage() for r in caplog.records if r.name == "opsdesk.tasks"]
        assert "task started" in messages
        assert "task retrying" in messages
        assert "task failed" in messages
        failed = next(r for r in caplog.records if r.getMessage() == "task failed")
        assert failed.task == "notifications.deliver"
