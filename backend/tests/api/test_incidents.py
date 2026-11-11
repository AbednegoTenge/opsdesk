from datetime import timedelta

import pytest
from django.utils import timezone

from apps.incidents.models import Comment, EventType, Incident, IncidentEvent, SLAPolicy, Status
from apps.users.models import Role

from ..factories import IncidentFactory, UserFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/incidents/"


def url(incident, suffix=""):
    return f"{URL}{incident.pk}/{suffix}"


def event_types(incident):
    return list(
        IncidentEvent.objects.filter(incident=incident).values_list("event_type", flat=True)
    )


# --- create -------------------------------------------------------------------
class TestCreate:
    def test_engineer_creates_incident(self, engineer, client_for):
        res = client_for(engineer).post(
            URL,
            {"title": "API 500s", "description": "Spike", "priority": "critical"},
            format="json",
        )
        assert res.status_code == 201
        body = res.data
        assert body["reference"] == f"INC-{body['id']:06d}"
        assert body["status"] == "open"
        assert body["sla_status"] == "ok"
        assert body["reporter"]["id"] == engineer.pk
        assert body["assignee"] is None

    def test_due_times_follow_sla_policy(self, engineer, client_for):
        res = client_for(engineer).post(URL, {"title": "x", "priority": "critical"}, format="json")
        incident = Incident.objects.get(pk=res.data["id"])
        assert incident.response_due_at - incident.created_at == timedelta(minutes=15)
        assert incident.resolve_due_at - incident.created_at == timedelta(hours=4)

    def test_records_created_and_assigned_events(self, admin, engineer, client_for):
        res = client_for(admin).post(URL, {"title": "x", "assignee_id": engineer.pk}, format="json")
        incident = Incident.objects.get(pk=res.data["id"])
        assert event_types(incident) == [EventType.CREATED, EventType.ASSIGNED]
        assert res.data["assignee"]["id"] == engineer.pk

    def test_default_priority_is_medium(self, engineer, client_for):
        assert (
            client_for(engineer).post(URL, {"title": "x"}, format="json").data["priority"]
            == "medium"
        )

    def test_viewer_cannot_create(self, viewer, client_for):
        assert client_for(viewer).post(URL, {"title": "x"}, format="json").status_code == 403
        assert Incident.objects.count() == 0

    def test_unauthenticated(self, api_client):
        assert api_client.post(URL, {"title": "x"}, format="json").status_code == 401

    @pytest.mark.parametrize(
        "body,field",
        [
            ({}, "title"),
            ({"title": "   "}, "title"),
            ({"title": "x" * 201}, "title"),
            ({"title": "x", "priority": "urgent"}, "priority"),
            ({"title": "x", "assignee_id": 999999}, "assignee_id"),
        ],
    )
    def test_validation(self, engineer, client_for, body, field):
        res = client_for(engineer).post(URL, body, format="json")
        assert res.status_code == 400
        assert field in res.data["error"]["details"]

    @pytest.mark.parametrize("bad", ["viewer", "inactive"])
    def test_assignee_must_be_active_engineer_or_admin(self, engineer, client_for, bad):
        target = (
            UserFactory(role=Role.VIEWER)
            if bad == "viewer"
            else UserFactory(role=Role.ENGINEER, is_active=False)
        )
        res = client_for(engineer).post(
            URL, {"title": "x", "assignee_id": target.pk}, format="json"
        )
        assert res.status_code == 400
        assert "assignee_id" in res.data["error"]["details"]
        assert Incident.objects.count() == 0


# --- list / filter / retrieve ------------------------------------------------------
class TestList:
    def test_all_roles_can_list(self, viewer, client_for):
        IncidentFactory.create_batch(3)
        res = client_for(viewer).get(URL)
        assert res.status_code == 200
        assert res.data["count"] == 3

    def test_filters(self, engineer, client_for):
        mine = IncidentFactory(title="Disk full on db-1", priority="high", assignee=engineer)
        IncidentFactory(title="Login broken", priority="low", status=Status.RESOLVED)
        unassigned = IncidentFactory(title="Queue backlog", priority="critical")
        client = client_for(engineer)

        def ids(**params):
            return {r["id"] for r in client.get(URL, params).data["results"]}

        assert ids(assignee="me") == {mine.pk}
        assert ids(assignee=str(engineer.pk)) == {mine.pk}
        assert unassigned.pk in ids(assignee="none")
        assert ids(status="open", priority="critical,high") == {mine.pk, unassigned.pk}
        assert ids(search="disk") == {mine.pk}
        assert ids(search=mine.reference) == {mine.pk}
        assert len(ids(status="open,resolved")) == 3

    def test_created_range(self, engineer, client_for):
        old = IncidentFactory()
        Incident.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=10))
        new = IncidentFactory()
        since = (timezone.now() - timedelta(days=1)).isoformat()
        res = client_for(engineer).get(URL, {"created_after": since})
        assert [r["id"] for r in res.data["results"]] == [new.pk]

    def test_order_by_priority_most_urgent_first(self, engineer, client_for):
        for p in ["low", "critical", "medium", "high"]:
            IncidentFactory(priority=p)
        res = client_for(engineer).get(URL, {"ordering": "priority"})
        assert [r["priority"] for r in res.data["results"]] == ["critical", "high", "medium", "low"]

    @pytest.mark.parametrize(
        "params",
        [{"status": "pending"}, {"priority": "p1"}, {"ordering": "title"}, {"assignee": "x"}],
    )
    def test_invalid_filters_are_rejected(self, engineer, client_for, params):
        res = client_for(engineer).get(URL, params)
        assert res.status_code == 400

    def test_paginated(self, engineer, client_for):
        IncidentFactory.create_batch(4)
        res = client_for(engineer).get(URL, {"page_size": 3})
        assert len(res.data["results"]) == 3
        assert res.data["next"]
        assert client_for(engineer).get(URL, {"page": 2, "page_size": 3}).data["results"]

    def test_list_query_count_does_not_grow_with_rows(
        self, engineer, client_for, django_assert_max_num_queries
    ):
        IncidentFactory.create_batch(10, assignee=engineer)
        client = client_for(engineer)
        with django_assert_max_num_queries(4):
            client.get(URL)

    def test_retrieve_detail(self, viewer, client_for):
        incident = IncidentFactory(description="Full details")
        res = client_for(viewer).get(url(incident))
        assert res.status_code == 200
        assert res.data["description"] == "Full details"
        assert "acknowledged_at" in res.data

    def test_retrieve_missing(self, viewer, client_for):
        assert client_for(viewer).get(f"{URL}424242/").status_code == 404


# --- update -------------------------------------------------------------------
class TestUpdate:
    def test_edit_title_records_event(self, engineer, client_for):
        incident = IncidentFactory(title="Old")
        res = client_for(engineer).patch(url(incident), {"title": "New"}, format="json")
        assert res.status_code == 200
        assert res.data["title"] == "New"
        event = IncidentEvent.objects.filter(incident=incident).last()
        assert event.event_type == EventType.UPDATED
        assert event.data["fields"]["title"] == {"from": "Old", "to": "New"}
        assert event.actor == engineer

    def test_priority_change_records_event_and_moves_due_times(self, engineer, client_for):
        incident = IncidentFactory(priority="low")
        client_for(engineer).patch(url(incident), {"priority": "critical"}, format="json")
        incident.refresh_from_db()
        assert incident.resolve_due_at - incident.created_at == timedelta(hours=4)
        assert event_types(incident)[-1] == EventType.PRIORITY_CHANGED

    def test_no_op_edit_writes_no_event(self, engineer, client_for):
        incident = IncidentFactory(title="Same")
        before = IncidentEvent.objects.count()
        client_for(engineer).patch(url(incident), {"title": "Same"}, format="json")
        assert IncidentEvent.objects.count() == before

    @pytest.mark.parametrize("field", ["status", "assignee_id"])
    def test_status_and_assignee_have_their_own_endpoints(self, engineer, client_for, field):
        res = client_for(engineer).patch(url(IncidentFactory()), {field: "x"}, format="json")
        assert res.status_code == 400
        assert field in res.data["error"]["details"]

    def test_empty_patch_rejected(self, engineer, client_for):
        assert (
            client_for(engineer).patch(url(IncidentFactory()), {}, format="json").status_code == 400
        )

    def test_closed_incident_cannot_be_edited(self, engineer, client_for):
        incident = IncidentFactory(status=Status.CLOSED)
        res = client_for(engineer).patch(url(incident), {"title": "x"}, format="json")
        assert res.status_code == 400

    def test_viewer_cannot_edit(self, viewer, client_for):
        res = client_for(viewer).patch(url(IncidentFactory()), {"title": "x"}, format="json")
        assert res.status_code == 403


class TestDelete:
    def test_admin_deletes(self, admin, client_for):
        incident = IncidentFactory()
        assert client_for(admin).delete(url(incident)).status_code == 204
        assert not Incident.objects.filter(pk=incident.pk).exists()

    @pytest.mark.parametrize("who", ["engineer", "viewer"])
    def test_others_cannot_delete(self, who, request, client_for):
        incident = IncidentFactory()
        assert client_for(request.getfixturevalue(who)).delete(url(incident)).status_code == 403
        assert Incident.objects.filter(pk=incident.pk).exists()


# --- assign -------------------------------------------------------------------
class TestAssign:
    def test_assign_and_reassign(self, admin, engineer, client_for):
        other = UserFactory(role=Role.ENGINEER)
        incident = IncidentFactory()
        client = client_for(admin)
        assert (
            client.post(
                url(incident, "assign/"), {"assignee_id": engineer.pk}, format="json"
            ).status_code
            == 200
        )
        res = client.post(url(incident, "assign/"), {"assignee_id": other.pk}, format="json")
        assert res.data["assignee"]["id"] == other.pk
        last = IncidentEvent.objects.filter(incident=incident).last()
        assert last.event_type == EventType.ASSIGNED
        assert last.data["from"]["id"] == engineer.pk
        assert last.data["to"]["id"] == other.pk

    def test_same_assignee_is_a_no_op(self, engineer, client_for):
        incident = IncidentFactory(assignee=engineer)
        before = event_types(incident)
        client_for(engineer).post(
            url(incident, "assign/"), {"assignee_id": engineer.pk}, format="json"
        )
        assert event_types(incident) == before

    def test_unassign(self, engineer, client_for):
        incident = IncidentFactory(assignee=engineer)
        res = client_for(engineer).post(
            url(incident, "assign/"), {"assignee_id": None}, format="json"
        )
        assert res.data["assignee"] is None
        assert event_types(incident)[-1] == EventType.UNASSIGNED

    def test_cannot_assign_viewer(self, engineer, viewer, client_for):
        res = client_for(engineer).post(
            url(IncidentFactory(), "assign/"), {"assignee_id": viewer.pk}, format="json"
        )
        assert res.status_code == 400

    def test_viewer_cannot_assign(self, viewer, engineer, client_for):
        res = client_for(viewer).post(
            url(IncidentFactory(), "assign/"), {"assignee_id": engineer.pk}, format="json"
        )
        assert res.status_code == 403

    def test_missing_body(self, engineer, client_for):
        assert (
            client_for(engineer)
            .post(url(IncidentFactory(), "assign/"), {}, format="json")
            .status_code
            == 400
        )


# --- transitions --------------------------------------------------------------
def move(client, incident, to, note=""):
    return client.post(url(incident, "transition/"), {"status": to, "note": note}, format="json")


class TestTransition:
    def test_start_work_takes_unassigned_incident_and_acknowledges(self, engineer, client_for):
        incident = IncidentFactory()
        res = move(client_for(engineer), incident, "in_progress")
        assert res.status_code == 200
        assert res.data["status"] == "in_progress"
        assert res.data["assignee"]["id"] == engineer.pk
        assert res.data["acknowledged_at"] is not None
        assert event_types(incident)[-2:] == [EventType.ASSIGNED, EventType.STATUS_CHANGED]

    def test_full_lifecycle(self, engineer, client_for):
        incident = IncidentFactory()
        client = client_for(engineer)
        assert move(client, incident, "in_progress").status_code == 200
        res = move(client, incident, "resolved", note="Restarted the pool")
        assert res.data["resolved_at"] is not None
        assert Comment.objects.filter(incident=incident, body="Restarted the pool").exists()
        res = move(client, incident, "closed")
        assert res.data["closed_at"] is not None

    def test_reopen_resolved_clears_resolution(self, engineer, client_for):
        incident = IncidentFactory()
        client = client_for(engineer)
        move(client, incident, "resolved")
        res = move(client, incident, "in_progress")
        assert res.status_code == 200
        assert res.data["resolved_at"] is None

    @pytest.mark.parametrize(
        "start,to",
        [
            ("open", "closed"),
            ("in_progress", "open"),
            ("in_progress", "closed"),
            ("resolved", "open"),
            ("closed", "resolved"),
            ("closed", "open"),
        ],
    )
    def test_invalid_transitions(self, engineer, client_for, start, to):
        incident = IncidentFactory(status=start)
        res = move(client_for(engineer), incident, to)
        assert res.status_code == 400
        assert res.data["error"]["details"]["status"]
        incident.refresh_from_db()
        assert incident.status == start

    def test_same_status_rejected(self, engineer, client_for):
        assert move(client_for(engineer), IncidentFactory(), "open").status_code == 400

    def test_only_admin_reopens_closed(self, admin, engineer, client_for):
        incident = IncidentFactory(status=Status.CLOSED)
        assert move(client_for(engineer), incident, "in_progress").status_code == 403
        assert move(client_for(admin), incident, "in_progress").status_code == 200

    def test_viewer_cannot_transition(self, viewer, client_for):
        assert move(client_for(viewer), IncidentFactory(), "resolved").status_code == 403


# --- comments and history -----------------------------------------------------------
class TestComments:
    def test_add_and_list(self, engineer, viewer, client_for):
        incident = IncidentFactory()
        res = client_for(engineer).post(
            url(incident, "comments/"), {"body": "Looking"}, format="json"
        )
        assert res.status_code == 201
        assert res.data["author"]["id"] == engineer.pk
        listing = client_for(viewer).get(url(incident, "comments/"))
        assert [c["body"] for c in listing.data["results"]] == ["Looking"]
        assert event_types(incident)[-1] == EventType.COMMENT_ADDED

    def test_viewer_cannot_comment(self, viewer, client_for):
        res = client_for(viewer).post(
            url(IncidentFactory(), "comments/"), {"body": "x"}, format="json"
        )
        assert res.status_code == 403

    def test_blank_comment_rejected(self, engineer, client_for):
        res = client_for(engineer).post(
            url(IncidentFactory(), "comments/"), {"body": "  "}, format="json"
        )
        assert res.status_code == 400

    def test_author_edits_and_deletes(self, engineer, client_for):
        incident = IncidentFactory()
        client = client_for(engineer)
        cid = client.post(url(incident, "comments/"), {"body": "v1"}, format="json").data["id"]
        res = client.patch(url(incident, f"comments/{cid}/"), {"body": "v2"}, format="json")
        assert res.data["body"] == "v2"
        assert res.data["edited_at"] is not None
        assert client.delete(url(incident, f"comments/{cid}/")).status_code == 204
        assert event_types(incident)[-2:] == [EventType.COMMENT_EDITED, EventType.COMMENT_DELETED]

    def test_other_engineer_cannot_edit_but_admin_can(self, engineer, admin, client_for):
        incident = IncidentFactory()
        cid = (
            client_for(engineer)
            .post(url(incident, "comments/"), {"body": "v1"}, format="json")
            .data["id"]
        )
        other = client_for(UserFactory(role=Role.ENGINEER))
        assert (
            other.patch(url(incident, f"comments/{cid}/"), {"body": "x"}, format="json").status_code
            == 403
        )
        assert other.delete(url(incident, f"comments/{cid}/")).status_code == 403
        assert (
            client_for(admin)
            .patch(url(incident, f"comments/{cid}/"), {"body": "mod"}, format="json")
            .status_code
            == 200
        )

    def test_comment_must_belong_to_incident(self, engineer, client_for):
        a, b = IncidentFactory(), IncidentFactory()
        cid = (
            client_for(engineer).post(url(a, "comments/"), {"body": "x"}, format="json").data["id"]
        )
        assert client_for(engineer).delete(url(b, f"comments/{cid}/")).status_code == 404


def test_activity_history_is_chronological(engineer, viewer, client_for):
    incident = IncidentFactory(reporter=engineer)
    client = client_for(engineer)
    client.patch(url(incident), {"priority": "high"}, format="json")
    move(client, incident, "in_progress")
    client.post(url(incident, "comments/"), {"body": "on it"}, format="json")
    move(client, incident, "resolved")

    res = client_for(viewer).get(url(incident, "events/"))
    assert res.status_code == 200
    assert [e["event_type"] for e in res.data["results"]] == [
        "created",
        "priority_changed",
        "assigned",
        "status_changed",
        "comment_added",
        "status_changed",
    ]
    assert res.data["results"][1]["data"] == {"from": "medium", "to": "high"}
    assert res.data["results"][0]["actor"]["id"] == engineer.pk


# --- SLA policies ------------------------------------------------------------------
class TestSLAPolicies:
    def test_defaults_listed_by_urgency(self, viewer, client_for):
        res = client_for(viewer).get("/api/v1/sla-policies/")
        assert res.status_code == 200
        assert [
            (p["priority"], p["response_minutes"], p["resolution_minutes"]) for p in res.data
        ] == [
            ("critical", 15, 240),
            ("high", 60, 480),
            ("medium", 240, 1440),
            ("low", 1440, 4320),
        ]

    def test_admin_updates(self, admin, client_for):
        res = client_for(admin).patch(
            "/api/v1/sla-policies/high/", {"response_minutes": 30}, format="json"
        )
        assert res.status_code == 200
        assert SLAPolicy.objects.get(priority="high").response_minutes == 30

    def test_resolution_cannot_be_shorter_than_response(self, admin, client_for):
        res = client_for(admin).patch(
            "/api/v1/sla-policies/low/", {"resolution_minutes": 10}, format="json"
        )
        assert res.status_code == 400

    def test_engineer_cannot_update(self, engineer, client_for):
        res = client_for(engineer).patch(
            "/api/v1/sla-policies/high/", {"response_minutes": 1}, format="json"
        )
        assert res.status_code == 403
