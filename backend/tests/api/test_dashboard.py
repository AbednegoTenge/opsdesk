from datetime import timedelta

import pytest
from django.utils import timezone

from apps.incidents.models import Incident, SLAStatus, Status
from apps.sla import services as sla
from apps.users.models import Role

from ..factories import IncidentFactory, UserFactory

pytestmark = pytest.mark.django_db
URL = "/api/v1/dashboard/"


@pytest.fixture
def fleet(engineer):
    """A small, known set of incidents."""
    other = UserFactory(role=Role.ENGINEER, email="zed@example.com")
    IncidentFactory(priority="critical", assignee=engineer)  # open, critical
    IncidentFactory(priority="high", assignee=engineer, status=Status.IN_PROGRESS)
    IncidentFactory(priority="low")  # open, unassigned
    IncidentFactory(
        priority="critical", assignee=other, status=Status.RESOLVED, resolved_at=timezone.now()
    )
    IncidentFactory(priority="medium", status=Status.CLOSED)
    return {"engineer": engineer, "other": other}


class TestSummary:
    def test_counts(self, fleet, viewer, client_for):
        res = client_for(viewer).get(f"{URL}summary/")
        assert res.status_code == 200
        d = res.data
        assert d["total"] == 5
        assert d["active"] == 3
        assert d["by_status"] == {"open": 2, "in_progress": 1, "resolved": 1, "closed": 1}
        assert d["critical"] == {"total": 2, "active": 1}
        assert d["active_by_priority"] == {"critical": 1, "high": 1, "medium": 0, "low": 1}
        assert d["unassigned_active"] == 1
        assert d["sla"] == {"breached_active": 0, "at_risk_active": 0}

    def test_sla_figures(self, viewer, client_for):
        incident = IncidentFactory(priority="critical")
        Incident.objects.filter(pk=incident.pk).update(
            response_due_at=timezone.now() - timedelta(minutes=1)
        )
        sla.check_sla()
        assert client_for(viewer).get(f"{URL}summary/").data["sla"]["breached_active"] == 1

    def test_empty(self, viewer, client_for):
        d = client_for(viewer).get(f"{URL}summary/").data
        assert d["total"] == 0
        assert d["active"] == 0

    def test_constant_query_count(self, fleet, viewer, client_for, django_assert_max_num_queries):
        IncidentFactory.create_batch(20)
        client = client_for(viewer)
        with django_assert_max_num_queries(2):  # auth user + one aggregate
            client.get(f"{URL}summary/")

    def test_requires_auth(self, api_client):
        assert api_client.get(f"{URL}summary/").status_code == 401


class TestByAssignee:
    def test_per_engineer_load(self, fleet, admin, client_for):
        res = client_for(admin).get(f"{URL}by-assignee/")
        assert res.status_code == 200
        rows = {r["email"]: r for r in res.data["engineers"]}
        e = rows[fleet["engineer"].email]
        assert (e["active"], e["in_progress"], e["critical_active"]) == (2, 1, 1)
        z = rows["zed@example.com"]
        assert (z["active"], z["resolved_recent"]) == (0, 1)
        assert res.data["unassigned_active"] == 1
        # Engineers with no work still appear, so the page can show who is free.
        assert admin.email in rows
        # Busiest first.
        assert res.data["engineers"][0]["email"] == fleet["engineer"].email

    def test_viewers_and_inactive_users_are_not_listed(self, fleet, viewer, client_for):
        UserFactory(role=Role.ENGINEER, is_active=False, email="gone@example.com")
        emails = {
            r["email"] for r in client_for(viewer).get(f"{URL}by-assignee/").data["engineers"]
        }
        assert viewer.email not in emails
        assert "gone@example.com" not in emails

    def test_breached_counts(self, engineer, viewer, client_for):
        incident = IncidentFactory(priority="critical", assignee=engineer)
        Incident.objects.filter(pk=incident.pk).update(sla_status=SLAStatus.BREACHED)
        rows = client_for(viewer).get(f"{URL}by-assignee/").data["engineers"]
        assert next(r for r in rows if r["id"] == engineer.pk)["breached_active"] == 1

    def test_constant_query_count(self, fleet, viewer, client_for, django_assert_max_num_queries):
        UserFactory.create_batch(10, role=Role.ENGINEER)
        IncidentFactory.create_batch(10, assignee=fleet["engineer"])
        client = client_for(viewer)
        with django_assert_max_num_queries(3):
            client.get(f"{URL}by-assignee/")


class TestTrends:
    def test_daily_series(self, engineer, viewer, client_for):
        now = timezone.now()
        a = IncidentFactory(assignee=engineer)
        b = IncidentFactory()
        IncidentFactory()
        Incident.objects.filter(pk=a.pk).update(
            created_at=now - timedelta(days=2, hours=3),
            resolved_at=now - timedelta(days=2),
            status=Status.RESOLVED,
        )
        Incident.objects.filter(pk=b.pk).update(created_at=now - timedelta(days=40))

        res = client_for(viewer).get(f"{URL}trends/", {"days": 7})
        assert res.status_code == 200
        d = res.data
        assert len(d["series"]) == 7
        assert d["series"][-1]["date"] == now.date().isoformat()
        assert d["totals"]["created"] == 2  # b is outside the window
        assert d["totals"]["resolved"] == 1
        assert 3 * 3600 - 60 < d["mean_time_to_resolve_seconds"] < 3 * 3600 + 60
        assert sum(r["created"] for r in d["series"]) == 2

    def test_days_with_nothing_are_zero_not_missing(self, viewer, client_for):
        d = client_for(viewer).get(f"{URL}trends/", {"days": 3}).data
        assert [r["created"] for r in d["series"]] == [0, 0, 0]
        assert d["mean_time_to_resolve_seconds"] is None

    def test_default_is_30_days(self, viewer, client_for):
        assert len(client_for(viewer).get(f"{URL}trends/").data["series"]) == 30

    @pytest.mark.parametrize("days", ["0", "366", "abc"])
    def test_invalid_days(self, viewer, client_for, days):
        assert client_for(viewer).get(f"{URL}trends/", {"days": days}).status_code == 400

    def test_constant_query_count(self, viewer, client_for, django_assert_max_num_queries):
        IncidentFactory.create_batch(15)
        client = client_for(viewer)
        with django_assert_max_num_queries(5):
            client.get(f"{URL}trends/", {"days": 90})
