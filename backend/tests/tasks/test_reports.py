from datetime import UTC, datetime, timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.incidents.models import Incident, Status
from apps.reporting import services
from apps.reporting.models import IncidentReport, ReportKind, ReportStatus
from apps.reporting.tasks import generate_report, schedule_periodic_report
from apps.sla import services as sla
from apps.users.models import Role
from opsdesk_tasks.models import OutboxMessage

from ..factories import IncidentFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestPeriods:
    def test_daily_is_yesterday_utc(self):
        start, end = services.previous_period("daily", datetime(2026, 11, 11, 7, 0, tzinfo=UTC))
        assert (start, end) == (
            datetime(2026, 11, 10, tzinfo=UTC),
            datetime(2026, 11, 11, tzinfo=UTC),
        )

    def test_weekly_is_last_monday_to_monday(self):
        # 2026-11-11 is a Wednesday.
        start, end = services.previous_period("weekly", datetime(2026, 11, 11, 7, 0, tzinfo=UTC))
        assert (start, end) == (
            datetime(2026, 11, 2, tzinfo=UTC),
            datetime(2026, 11, 9, tzinfo=UTC),
        )

    def test_adhoc_has_no_automatic_period(self):
        with pytest.raises(ValueError):
            services.previous_period("adhoc")


def window():
    now = timezone.now()
    return now - timedelta(days=1), now + timedelta(minutes=1)


class TestReportData:
    def test_counts_and_times(self):
        engineer = UserFactory(role=Role.ENGINEER, email="e@example.com")
        a = IncidentFactory(priority="critical", assignee=engineer)
        b = IncidentFactory(priority="low", assignee=engineer)
        IncidentFactory(priority="low")
        two_hours_ago = timezone.now() - timedelta(hours=2)
        Incident.objects.filter(pk=a.pk).update(
            created_at=two_hours_ago,
            acknowledged_at=two_hours_ago + timedelta(minutes=10),
            resolved_at=timezone.now(),
            status=Status.RESOLVED,
        )
        Incident.objects.filter(pk=b.pk).update(created_at=two_hours_ago)
        sla.check_sla()  # b and the third incident are fine; nothing breached

        data = services.build_report_data(*window())
        assert data["created"] == 3
        assert data["resolved"] == 1
        assert data["created_by_priority"] == {"critical": 1, "high": 0, "medium": 0, "low": 2}
        assert 7000 < data["mean_time_to_resolve_seconds"] < 7300
        assert data["mean_time_to_acknowledge_seconds"] == 600.0
        assert data["open_now"] == 2
        assert data["sla_breaches"]["total"] == 0
        assert data["per_engineer"] == [
            {
                "user_id": engineer.pk,
                "email": "e@example.com",
                "name": engineer.full_name,
                "open": 1,
                "resolved_in_period": 1,
            }
        ]

    def test_counts_sla_breaches_in_period(self):
        incident = IncidentFactory(priority="critical")
        Incident.objects.filter(pk=incident.pk).update(
            response_due_at=timezone.now() - timedelta(minutes=1)
        )
        sla.check_sla()
        data = services.build_report_data(*window())
        assert data["sla_breaches"] == {"total": 1, "response": 1, "resolution": 0}

    def test_empty_period(self):
        data = services.build_report_data(*window())
        assert data["created"] == 0
        assert data["mean_time_to_resolve_seconds"] is None


class TestGeneration:
    def test_request_is_idempotent(self):
        start, end = window()
        first, created1 = services.request_report(ReportKind.ADHOC, start, end)
        second, created2 = services.request_report(ReportKind.ADHOC, start, end)
        assert (created1, created2) == (True, False)
        assert first.pk == second.pk
        assert OutboxMessage.objects.filter(task_name="reporting.generate_report").count() == 1

    def test_generates_once_and_emails_admins_for_scheduled_reports(
        self, django_capture_on_commit_callbacks
    ):
        UserFactory(role=Role.ADMIN, email="boss@example.com")
        UserFactory(role=Role.ENGINEER, email="eng@example.com")
        start, end = window()
        report = IncidentReport.objects.create(
            kind=ReportKind.DAILY, period_start=start, period_end=end
        )
        with django_capture_on_commit_callbacks(execute=True):
            assert generate_report.apply(kwargs={"report_id": report.pk}).get() == "completed"
            assert (
                generate_report.apply(kwargs={"report_id": report.pk}).get() == "already_completed"
            )
        report.refresh_from_db()
        assert report.status == ReportStatus.COMPLETED
        assert report.completed_at is not None
        assert "created" in report.data
        assert [m.to for m in mail.outbox] == [["boss@example.com"]]

    def test_adhoc_reports_are_not_emailed(self, django_capture_on_commit_callbacks):
        UserFactory(role=Role.ADMIN)
        start, end = window()
        report = IncidentReport.objects.create(
            kind=ReportKind.ADHOC, period_start=start, period_end=end
        )
        with django_capture_on_commit_callbacks(execute=True):
            generate_report.apply(kwargs={"report_id": report.pk})
        assert mail.outbox == []

    def test_bug_marks_report_failed(self, monkeypatch):
        def boom(*a):
            raise ValueError("bad aggregate")

        monkeypatch.setattr(services, "build_report_data", boom)
        start, end = window()
        report = IncidentReport.objects.create(
            kind=ReportKind.ADHOC, period_start=start, period_end=end
        )
        assert generate_report.apply(kwargs={"report_id": report.pk}).failed()
        report.refresh_from_db()
        assert report.status == ReportStatus.FAILED
        assert "bad aggregate" in report.error

    def test_transient_error_retries_then_completes(self, monkeypatch):
        real, calls = services.build_report_data, {"n": 0}

        def flaky(*a):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("db blip")
            return real(*a)

        monkeypatch.setattr(services, "build_report_data", flaky)
        start, end = window()
        report = IncidentReport.objects.create(
            kind=ReportKind.ADHOC, period_start=start, period_end=end
        )
        assert generate_report.apply(kwargs={"report_id": report.pk}).get() == "completed"
        assert calls["n"] == 2

    def test_beat_entry_point_creates_previous_day_once(self, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            first = schedule_periodic_report.apply(kwargs={"kind": "daily"}).get()
            second = schedule_periodic_report.apply(kwargs={"kind": "daily"}).get()
        assert first["created"] is True
        assert second == {"report_id": first["report_id"], "created": False}
        report = IncidentReport.objects.get()
        assert report.status == ReportStatus.COMPLETED
        assert report.period_end - report.period_start == timedelta(days=1)


class TestReportsAPI:
    URL = "/api/v1/reports/"

    def body(self):
        start, end = window()
        return {"period_start": start.isoformat(), "period_end": end.isoformat()}

    def test_request_returns_202_without_waiting(
        self, admin, client_for, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=False):
            res = client_for(admin).post(self.URL, self.body(), format="json")
        assert res.status_code == 202
        assert res.data["status"] == "pending"
        assert res.data["kind"] == "adhoc"

    def test_report_is_ready_after_worker_runs(
        self, admin, engineer, client_for, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            rid = client_for(admin).post(self.URL, self.body(), format="json").data["id"]
        res = client_for(engineer).get(f"{self.URL}{rid}/")
        assert res.data["status"] == "completed"
        assert "created" in res.data["data"]

    def test_same_period_returns_existing_report(self, admin, client_for):
        body = self.body()
        first = client_for(admin).post(self.URL, body, format="json")
        second = client_for(admin).post(self.URL, body, format="json")
        assert second.status_code == 200
        assert second.data["id"] == first.data["id"]

    def test_list_omits_heavy_data(self, admin, client_for):
        client_for(admin).post(self.URL, self.body(), format="json")
        res = client_for(admin).get(self.URL)
        assert res.data["count"] == 1
        assert "data" not in res.data["results"][0]

    @pytest.mark.parametrize("start_offset,end_offset", [(0, -1), (0, 0), (-400, 0)])
    def test_invalid_periods(self, admin, client_for, start_offset, end_offset):
        now = timezone.now()
        body = {
            "period_start": (now + timedelta(days=start_offset)).isoformat(),
            "period_end": (now + timedelta(days=end_offset)).isoformat(),
        }
        assert client_for(admin).post(self.URL, body, format="json").status_code == 400

    def test_permissions(self, engineer, viewer, client_for):
        assert client_for(engineer).post(self.URL, self.body(), format="json").status_code == 403
        assert client_for(viewer).get(self.URL).status_code == 403
        assert client_for(engineer).get(self.URL).status_code == 200
