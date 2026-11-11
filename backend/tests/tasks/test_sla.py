from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.incidents.models import EventType, Incident, IncidentEvent, SLAStatus, Status
from apps.sla import services
from apps.sla.tasks import check_breaches, send_reminders
from apps.users.models import Role

from ..factories import IncidentFactory, UserFactory

pytestmark = pytest.mark.django_db


def opened(minutes_ago, **kw):
    """An incident created `minutes_ago`, with due times recomputed from that moment."""
    from apps.incidents.services import compute_due_times

    incident = IncidentFactory(**kw)
    created = timezone.now() - timedelta(minutes=minutes_ago)
    due = compute_due_times(incident.priority, created)
    Incident.objects.filter(pk=incident.pk).update(
        created_at=created, response_due_at=due.response_due_at, resolve_due_at=due.resolve_due_at
    )
    incident.refresh_from_db()
    return incident


def breach_events(incident):
    return IncidentEvent.objects.filter(incident=incident, event_type=EventType.SLA_BREACHED)


@pytest.fixture
def admin_user(db):
    return UserFactory(role=Role.ADMIN, email="boss@example.com")


@pytest.fixture
def oncall(db):
    return UserFactory(role=Role.ENGINEER, email="oncall@example.com")


class TestSLAMonitor:
    def test_unacknowledged_past_response_target_is_breached(
        self, admin_user, oncall, django_capture_on_commit_callbacks
    ):
        incident = opened(20, priority="critical", assignee=oncall)  # target 15 min
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            result = services.check_sla()
        assert result.response_breaches == [incident.pk]
        incident.refresh_from_db()
        assert incident.sla_status == SLAStatus.BREACHED
        assert incident.response_breached_at is not None
        event = breach_events(incident).get()
        assert event.actor is None
        assert event.data["target"] == "response"
        notified = sorted(m.to[0] for m in mail.outbox)
        assert notified == ["boss@example.com", "oncall@example.com"]

    def test_acknowledged_incident_meets_response_target(self, oncall):
        incident = opened(20, priority="critical", assignee=oncall)
        Incident.objects.filter(pk=incident.pk).update(
            status=Status.IN_PROGRESS, acknowledged_at=incident.created_at + timedelta(minutes=5)
        )
        assert services.check_sla().response_breaches == []

    def test_resolution_breach(self):
        incident = opened(5 * 60, priority="critical")  # resolve target 4 h
        result = services.check_sla()
        assert incident.pk in result.resolution_breaches
        assert breach_events(incident).filter(data__target="resolution").count() == 1

    def test_each_target_is_flagged_only_once(self):
        incident = opened(5 * 60, priority="critical")  # both targets missed
        services.check_sla()
        services.check_sla()
        services.check_sla()
        assert breach_events(incident).count() == 2  # one response, one resolution

    def test_concurrent_runs_flag_once(self):
        incident = opened(20, priority="critical")
        now = timezone.now()
        assert services._flag_breach(incident.pk, "response", now) is True
        assert services._flag_breach(incident.pk, "response", now) is False
        assert breach_events(incident).count() == 1

    @pytest.mark.parametrize("status", [Status.RESOLVED, Status.CLOSED])
    def test_finished_incidents_are_not_checked(self, status):
        incident = opened(10 * 60, priority="critical", status=status)
        services.check_sla()
        assert not breach_events(incident).exists()

    def test_incident_within_targets_is_left_alone(self):
        incident = opened(5, priority="critical")
        services.check_sla()
        incident.refresh_from_db()
        assert incident.sla_status == SLAStatus.OK

    def test_at_risk_after_three_quarters_of_window(self, oncall):
        risky = opened(int(4 * 60 * 0.8), priority="critical", assignee=oncall)
        fine = opened(int(72 * 60 * 0.5), priority="low", assignee=oncall)
        for i in (risky, fine):
            Incident.objects.filter(pk=i.pk).update(acknowledged_at=i.created_at)
        result = services.check_sla()
        risky.refresh_from_db()
        fine.refresh_from_db()
        assert risky.sla_status == SLAStatus.AT_RISK
        assert fine.sla_status == SLAStatus.OK
        assert result.at_risk == 1
        assert not breach_events(risky).exists()  # at risk is a status, not an event

    def test_breach_appears_in_history_api(self, oncall, client_for):
        incident = opened(20, priority="critical")
        services.check_sla()
        res = client_for(oncall).get(f"/api/v1/incidents/{incident.pk}/events/")
        last = res.data["results"][-1]
        assert last["event_type"] == "sla_breached"
        assert last["actor"] is None

    def test_task_wrapper(self):
        opened(20, priority="critical")
        assert check_breaches.apply().get() == {
            "response_breaches": 1,
            "resolution_breaches": 0,
            "at_risk": 0,
        }


class TestReminders:
    def test_reminds_assignee_once_per_interval(self, oncall, django_capture_on_commit_callbacks):
        incident = opened(31, priority="critical", assignee=oncall)  # interval 30 min
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            assert services.send_reminders() == [incident.pk]
            assert services.send_reminders() == []  # same interval: no duplicate
        assert [m.to for m in mail.outbox] == [["oncall@example.com"]]
        assert "Reminder" in mail.outbox[0].subject
        incident.refresh_from_db()
        assert incident.last_reminded_at is not None

    def test_reminds_again_after_the_interval(self, oncall):
        incident = opened(31, priority="critical", assignee=oncall)
        now = timezone.now()
        assert services.send_reminders(now) == [incident.pk]
        assert services.send_reminders(now + timedelta(minutes=10)) == []
        assert services.send_reminders(now + timedelta(minutes=31)) == [incident.pk]
        assert (
            IncidentEvent.objects.filter(
                incident=incident, event_type=EventType.REMINDER_SENT
            ).count()
            == 2
        )

    def test_not_before_first_interval(self, oncall):
        opened(10, priority="critical", assignee=oncall)
        assert services.send_reminders() == []

    def test_only_priorities_with_a_reminder_interval(self, oncall):
        opened(10 * 60, priority="medium", assignee=oncall)
        opened(10 * 60, priority="low", assignee=oncall)
        assert services.send_reminders() == []

    def test_high_priority_uses_its_own_interval(self, oncall):
        opened(45, priority="high", assignee=oncall)  # interval 60 min
        assert services.send_reminders() == []
        incident = opened(61, priority="high", assignee=oncall)
        assert services.send_reminders() == [incident.pk]

    @pytest.mark.parametrize("status", [Status.RESOLVED, Status.CLOSED])
    def test_resolved_incidents_get_no_reminders(self, oncall, status):
        opened(120, priority="critical", assignee=oncall, status=status)
        assert services.send_reminders() == []

    def test_unassigned_incident_reminds_admins(
        self, admin_user, django_capture_on_commit_callbacks
    ):
        opened(31, priority="critical")
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            services.send_reminders()
        assert [m.to for m in mail.outbox] == [["boss@example.com"]]

    def test_task_wrapper(self, oncall):
        opened(31, priority="critical", assignee=oncall)
        assert send_reminders.apply().get() == 1
