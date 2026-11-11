import pytest
from django.utils import timezone

from apps.notifications.models import Notification

from ..factories import UserFactory

pytestmark = pytest.mark.django_db
URL = "/api/v1/notifications/"


def note(user, **kw):
    return Notification.objects.create(recipient=user, kind="incident_assigned", title="t", **kw)


def test_lists_only_my_notifications(engineer, viewer, client_for):
    mine = note(engineer)
    note(viewer)
    res = client_for(engineer).get(URL)
    assert [n["id"] for n in res.data["results"]] == [mine.pk]


def test_unread_filter_and_count(engineer, client_for):
    note(engineer)
    note(engineer, read_at=timezone.now())
    client = client_for(engineer)
    assert client.get(URL, {"unread": "true"}).data["count"] == 1
    assert client.get(f"{URL}unread-count/").data == {"unread": 1}


def test_mark_some_read(engineer, client_for):
    a, b = note(engineer), note(engineer)
    res = client_for(engineer).post(f"{URL}mark-read/", {"ids": [a.pk]}, format="json")
    assert res.data == {"updated": 1}
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.read_at and not b.read_at


def test_mark_all_read(engineer, client_for):
    note(engineer)
    note(engineer)
    assert client_for(engineer).post(f"{URL}mark-read/", {"all": True}, format="json").data == {
        "updated": 2
    }


def test_cannot_mark_someone_elses(engineer, client_for):
    theirs = note(UserFactory())
    res = client_for(engineer).post(f"{URL}mark-read/", {"ids": [theirs.pk]}, format="json")
    assert res.data == {"updated": 0}
    theirs.refresh_from_db()
    assert theirs.read_at is None


def test_mark_read_needs_ids_or_all(engineer, client_for):
    assert client_for(engineer).post(f"{URL}mark-read/", {}, format="json").status_code == 400


def test_requires_auth(api_client):
    assert api_client.get(URL).status_code == 401
