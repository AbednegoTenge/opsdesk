import pytest
from django.conf import settings
from django.test import override_settings

from apps.users.models import Role, User

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register/"
LOGIN = "/api/v1/auth/token/"
REFRESH = "/api/v1/auth/token/refresh/"
LOGOUT = "/api/v1/auth/logout/"
ME = "/api/v1/auth/me/"
PASSWORD = "/api/v1/auth/password/change/"
COOKIE = settings.REFRESH_COOKIE_NAME


def login(client, email, password):
    return client.post(LOGIN, {"email": email, "password": password}, format="json")


class TestRegistration:
    def test_creates_viewer_and_never_returns_password(self, api_client):
        res = api_client.post(
            REGISTER,
            {"email": "New@Example.com", "full_name": "New Person", "password": "a-Long-pass-123"},
            format="json",
        )
        assert res.status_code == 201
        assert res.data["email"] == "new@example.com"
        assert res.data["role"] == Role.VIEWER
        assert "password" not in res.data
        user = User.objects.get(email="new@example.com")
        assert user.password != "a-Long-pass-123"  # stored hashed
        assert user.check_password("a-Long-pass-123")

    def test_cannot_choose_own_role(self, api_client):
        res = api_client.post(
            REGISTER,
            {"email": "sneaky@example.com", "password": "a-Long-pass-123", "role": "admin"},
            format="json",
        )
        assert res.status_code == 201
        assert User.objects.get(email="sneaky@example.com").role == Role.VIEWER

    @pytest.mark.parametrize("pwd", ["short1", "password123", "1234567890123"])
    def test_rejects_weak_passwords(self, api_client, pwd):
        res = api_client.post(REGISTER, {"email": "w@example.com", "password": pwd}, format="json")
        assert res.status_code == 400
        assert res.data["error"]["code"] == "validation_error"

    def test_rejects_duplicate_email_case_insensitively(self, api_client, viewer):
        res = api_client.post(
            REGISTER, {"email": viewer.email.upper(), "password": "a-Long-pass-123"}, format="json"
        )
        assert res.status_code == 400
        assert "email" in res.data["error"]["details"]

    def test_rejects_missing_fields(self, api_client):
        res = api_client.post(REGISTER, {}, format="json")
        assert res.status_code == 400
        assert set(res.data["error"]["details"]) >= {"email", "password"}

    @override_settings(ALLOW_REGISTRATION=False)
    def test_can_be_disabled(self, api_client):
        res = api_client.post(
            REGISTER, {"email": "x@example.com", "password": "a-Long-pass-123"}, format="json"
        )
        assert res.status_code == 403
        assert not User.objects.filter(email="x@example.com").exists()


class TestLogin:
    def test_returns_access_token_and_sets_httponly_refresh_cookie(
        self, api_client, engineer, password
    ):
        res = login(api_client, engineer.email, password)
        assert res.status_code == 200
        assert res.data["access"]
        assert res.data["user"]["role"] == Role.ENGINEER
        assert "refresh" not in res.data  # never exposed to JavaScript
        cookie = res.cookies[COOKIE]
        assert cookie["httponly"]
        assert cookie["path"] == "/api/v1/auth/"

    def test_records_refresh_token_in_redis(self, api_client, engineer, password, fake_redis):
        login(api_client, engineer.email, password)
        assert (
            len(fake_redis.smembers(f"{settings.REFRESH_TOKEN_KEY_PREFIX}:user:{engineer.pk}")) == 1
        )

    def test_email_is_case_insensitive(self, api_client, engineer, password):
        assert login(api_client, engineer.email.upper(), password).status_code == 200

    @pytest.mark.parametrize(
        "email,pwd", [("engineer@example.com", "wrong"), ("nobody@x.com", "x")]
    )
    def test_bad_credentials_get_one_generic_error(self, api_client, engineer, email, pwd):
        res = login(api_client, email, pwd)
        assert res.status_code == 401
        assert res.data["error"]["message"] == "Invalid email or password."

    def test_inactive_user_cannot_log_in(self, api_client, engineer, password):
        engineer.is_active = False
        engineer.save()
        assert login(api_client, engineer.email, password).status_code == 401

    def test_access_token_authenticates_requests(self, api_client, engineer, password):
        access = login(api_client, engineer.email, password).data["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        res = api_client.get(ME)
        assert res.status_code == 200
        assert res.data["email"] == engineer.email

    def test_garbage_bearer_token_is_rejected(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-jwt")
        assert api_client.get(ME).status_code == 401

    def test_token_signed_with_another_key_is_rejected(self, api_client, engineer):
        import jwt
        from rest_framework_simplejwt.tokens import AccessToken

        claims = dict(AccessToken.for_user(engineer).payload)
        forged = jwt.encode(claims, "an-attacker-key-that-is-long-enough!", algorithm="HS256")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {forged}")
        assert api_client.get(ME).status_code == 401

    def test_token_for_another_audience_is_rejected(self, api_client, engineer):
        import jwt
        from rest_framework_simplejwt.tokens import AccessToken

        claims = {**AccessToken.for_user(engineer).payload, "aud": "some-other-service"}
        token = jwt.encode(claims, settings.SIMPLE_JWT["SIGNING_KEY"], algorithm="HS256")
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        assert api_client.get(ME).status_code == 401


class TestRefresh:
    def test_rotates_tokens(self, api_client, engineer, password):
        first = login(api_client, engineer.email, password)
        old_cookie = first.cookies[COOKIE].value
        res = api_client.post(REFRESH)
        assert res.status_code == 200
        assert res.data["access"]
        assert res.cookies[COOKIE].value != old_cookie

    def test_old_refresh_token_cannot_be_reused(self, api_client, engineer, password):
        old = login(api_client, engineer.email, password).cookies[COOKIE].value
        assert api_client.post(REFRESH).status_code == 200
        api_client.cookies.clear()
        res = api_client.post(REFRESH, {"refresh": old}, format="json")
        assert res.status_code == 401
        assert res.data["error"]["code"] == "token_revoked"

    def test_refresh_token_in_body_works_for_non_browser_clients(
        self, api_client, engineer, password
    ):
        raw = login(api_client, engineer.email, password).cookies[COOKIE].value
        api_client.cookies.clear()
        assert api_client.post(REFRESH, {"refresh": raw}, format="json").status_code == 200

    def test_missing_token(self, api_client):
        res = api_client.post(REFRESH)
        assert res.status_code == 401
        assert res.data["error"]["code"] == "no_refresh_token"

    def test_tampered_token(self, api_client):
        res = api_client.post(REFRESH, {"refresh": "abc.def.ghi"}, format="json")
        assert res.status_code == 401

    def test_deactivated_user_cannot_refresh(self, api_client, engineer, password):
        login(api_client, engineer.email, password)
        User.objects.filter(pk=engineer.pk).update(is_active=False)
        assert api_client.post(REFRESH).status_code == 401

    def test_store_outage_maps_to_503(self, api_client, engineer, password, redis_down):
        res = login(api_client, engineer.email, password)
        assert res.status_code == 503
        assert res.data["error"]["code"] == "service_unavailable"


@pytest.mark.django_db
def test_access_token_keeps_working_while_redis_is_down(engineer, client_for, request):
    client = client_for(engineer)  # issued while Redis is up

    request.getfixturevalue("redis_down")
    assert client.get(ME).status_code == 200


class TestLogout:
    def test_revokes_refresh_token_and_clears_cookie(self, api_client, engineer, password):
        raw = login(api_client, engineer.email, password).cookies[COOKIE].value
        res = api_client.post(LOGOUT)
        assert res.status_code == 204
        assert res.cookies[COOKIE].value == ""
        api_client.cookies.clear()
        assert api_client.post(REFRESH, {"refresh": raw}, format="json").status_code == 401

    def test_logout_without_token_is_harmless(self, api_client):
        assert api_client.post(LOGOUT).status_code == 204

    def test_logout_only_revokes_that_session(self, engineer, password):
        from rest_framework.test import APIClient

        laptop, phone = APIClient(), APIClient()
        login(laptop, engineer.email, password)
        login(phone, engineer.email, password)
        laptop.post(LOGOUT)
        assert phone.post(REFRESH).status_code == 200


class TestMe:
    def test_requires_authentication(self, api_client):
        res = api_client.get(ME)
        assert res.status_code == 401
        assert res.data["error"]["code"] == "not_authenticated"

    def test_update_name_but_not_role(self, viewer, client_for):
        client = client_for(viewer)
        res = client.patch(ME, {"full_name": "Renamed", "role": "admin"}, format="json")
        assert res.status_code == 200
        viewer.refresh_from_db()
        assert viewer.full_name == "Renamed"
        assert viewer.role == Role.VIEWER


class TestPasswordChange:
    def test_changes_password_and_revokes_all_sessions(self, api_client, engineer, password):
        from rest_framework.test import APIClient

        other = APIClient()
        login(other, engineer.email, password)
        access = login(api_client, engineer.email, password).data["access"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        res = api_client.post(
            PASSWORD, {"old_password": password, "new_password": "Brand-new-pass-42"}, format="json"
        )
        assert res.status_code == 204
        assert other.post(REFRESH).status_code == 401
        assert login(APIClient(), engineer.email, password).status_code == 401
        assert login(APIClient(), engineer.email, "Brand-new-pass-42").status_code == 200

    def test_wrong_old_password(self, engineer, client_for):
        res = client_for(engineer).post(
            PASSWORD, {"old_password": "nope", "new_password": "Brand-new-pass-42"}, format="json"
        )
        assert res.status_code == 400
        assert "old_password" in res.data["error"]["details"]

    def test_weak_new_password(self, engineer, client_for, password):
        res = client_for(engineer).post(
            PASSWORD, {"old_password": password, "new_password": "short"}, format="json"
        )
        assert res.status_code == 400
