"""Service-layer rules, especially that a change and its history commit or roll back together."""

import pytest

from apps.incidents import services
from apps.incidents.models import (
    AppendOnlyError,
    Comment,
    Incident,
    IncidentEvent,
    SLAPolicy,
    Status,
)
from apps.users.models import Role

from ..factories import IncidentFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def failing_event_write(monkeypatch):
    """Make the history write fail, as a DB error mid-transaction would."""

    def boom(*args, **kwargs):
        raise RuntimeError("event table unavailable")

    monkeypatch.setattr(IncidentEvent.objects, "create", boom)


def test_create_rolls_back_when_history_write_fails(failing_event_write):
    with pytest.raises(RuntimeError):
        services.create_incident(actor=UserFactory(role=Role.ENGINEER), title="x")
    assert Incident.objects.count() == 0


def test_transition_rolls_back_when_history_write_fails(monkeypatch):
    incident = IncidentFactory()
    engineer = UserFactory(role=Role.ENGINEER)
    monkeypatch.setattr(
        IncidentEvent.objects, "create", lambda **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    with pytest.raises(RuntimeError):
        services.transition_incident(
            incident_id=incident.pk, actor=engineer, to_status=Status.RESOLVED, note="done"
        )
    incident.refresh_from_db()
    assert incident.status == Status.OPEN
    assert incident.resolved_at is None
    assert not Comment.objects.filter(incident=incident).exists()


def test_assign_rolls_back_when_history_write_fails(monkeypatch):
    incident = IncidentFactory()
    engineer = UserFactory(role=Role.ENGINEER)
    monkeypatch.setattr(
        IncidentEvent.objects, "create", lambda **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    with pytest.raises(RuntimeError):
        services.assign_incident(incident_id=incident.pk, actor=engineer, assignee=engineer)
    incident.refresh_from_db()
    assert incident.assignee is None


def test_events_are_append_only():
    event = IncidentFactory().events.first()
    event.data = {"tampered": True}
    with pytest.raises(AppendOnlyError):
        event.save()


def test_reference_is_unique_and_sequential():
    a, b = IncidentFactory(), IncidentFactory()
    assert a.reference != b.reference
    assert a.reference.startswith("INC-")


def test_missing_policy_means_no_due_times():
    SLAPolicy.objects.filter(priority="low").delete()
    incident = services.create_incident(
        actor=UserFactory(role=Role.ENGINEER), title="x", priority="low"
    )
    assert incident.response_due_at is None
    assert incident.resolve_due_at is None


def test_update_rejects_unknown_fields():
    incident = IncidentFactory()
    with pytest.raises(services.IncidentRuleError):
        services.update_incident(
            incident_id=incident.pk, actor=UserFactory(role=Role.ENGINEER), status="closed"
        )


def test_resolving_from_open_also_acknowledges():
    incident = IncidentFactory()
    incident = services.transition_incident(
        incident_id=incident.pk, actor=UserFactory(role=Role.ENGINEER), to_status=Status.RESOLVED
    )
    assert incident.acknowledged_at is not None
    assert incident.acknowledged_at == incident.resolved_at
