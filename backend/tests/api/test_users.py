import pytest
from django.conf import settings

from apps.users.models import Role

from ..factories import UserFactory

pytestmark = pytest.mark.django_db

USERS = "/api/v1/users/"


def detail(user):
    return f"{USERS}{user.pk}/"


class TestListUsers:
    def test_unauthenticated(self, api_client):
        assert api_client.get(USERS).status_code == 401

    def test_viewer_forbidden(self, viewer, client_for):
        res = client_for(viewer).get(USERS)
        assert res.status_code == 403
        assert res.data["error"]["code"] == "permission_denied"

    @pytest.mark.parametrize("who", ["engineer", "admin"])
    def test_engineer_and_admin_allowed(self, who, request, client_for, viewer):
        user = request.getfixturevalue(who)
        res = client_for(user).get(USERS)
        assert res.status_code == 200
        assert res.data["count"] == 2

    def test_filter_by_role_for_assignee_picker(self, admin, engineer, viewer, client_for):
        UserFactory(role=Role.ENGINEER)
        res = client_for(admin).get(USERS, {"role": "engineer"})
        assert {u["role"] for u in res.data["results"]} == {"engineer"}
        assert res.data["count"] == 2

    def test_search(self, admin, client_for):
        UserFactory(email="alice@corp.io", full_name="Alice Ops")
        res = client_for(admin).get(USERS, {"search": "alice"})
        assert [u["email"] for u in res.data["results"]] == ["alice@corp.io"]

    def test_pagination(self, admin, client_for):
        UserFactory.create_batch(5)
        res = client_for(admin).get(USERS, {"page_size": 2})
        assert res.data["count"] == 6
        assert len(res.data["results"]) == 2
        assert res.data["next"]

    def test_page_size_is_capped(self, admin, client_for):
        UserFactory.create_batch(3)
        res = client_for(admin).get(USERS, {"page_size": 100000})
        assert res.status_code == 200
        assert len(res.data["results"]) == 4


class TestUpdateUsers:
    def test_admin_changes_role_and_old_sessions_are_revoked(
        self, admin, viewer, client_for, fake_redis
    ):
        from apps.users import token_store

        token_store.issue_for(viewer)
        res = client_for(admin).patch(detail(viewer), {"role": "engineer"}, format="json")
        assert res.status_code == 200
        assert res.data["role"] == "engineer"
        viewer.refresh_from_db()
        assert viewer.role == Role.ENGINEER
        assert not fake_redis.exists(f"{settings.REFRESH_TOKEN_KEY_PREFIX}:user:{viewer.pk}")

    def test_admin_deactivates_user(self, admin, engineer, client_for):
        res = client_for(admin).patch(detail(engineer), {"is_active": False}, format="json")
        assert res.status_code == 200
        engineer.refresh_from_db()
        assert engineer.is_active is False

    def test_deactivated_user_access_token_stops_working(self, admin, engineer, client_for):
        engineer_client = client_for(engineer)
        client_for(admin).patch(detail(engineer), {"is_active": False}, format="json")
        assert engineer_client.get("/api/v1/auth/me/").status_code == 401

    def test_invalid_role_rejected(self, admin, viewer, client_for):
        res = client_for(admin).patch(detail(viewer), {"role": "superuser"}, format="json")
        assert res.status_code == 400
        assert "role" in res.data["error"]["details"]

    @pytest.mark.parametrize("who", ["engineer", "viewer"])
    def test_non_admins_cannot_change_users(self, who, request, client_for):
        actor = request.getfixturevalue(who)
        target = UserFactory()
        res = client_for(actor).patch(detail(target), {"role": "admin"}, format="json")
        assert res.status_code == 403
        target.refresh_from_db()
        assert target.role == Role.VIEWER

    def test_admin_cannot_demote_or_deactivate_self(self, admin, client_for):
        client = client_for(admin)
        assert client.patch(detail(admin), {"role": "viewer"}, format="json").status_code == 400
        assert client.patch(detail(admin), {"is_active": False}, format="json").status_code == 400

    def test_put_and_delete_not_allowed(self, admin, viewer, client_for):
        client = client_for(admin)
        assert client.put(detail(viewer), {}, format="json").status_code == 405
        assert client.delete(detail(viewer)).status_code == 405

    def test_create_through_users_endpoint_not_allowed(self, admin, client_for):
        assert client_for(admin).post(USERS, {}, format="json").status_code == 405

    def test_unknown_user_404(self, admin, client_for):
        res = client_for(admin).get(f"{USERS}999999/")
        assert res.status_code == 404
        assert res.data["error"]["code"] == "not_found"
