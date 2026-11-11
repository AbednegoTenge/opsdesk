"""Rate limits on the sign-in endpoints and security headers on every response."""

import pytest
from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle

from apps.core import throttling

from ..factories import DEFAULT_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/token/"
WRONG_PASSWORD = "not-the-password"  # noqa: S105 - test value


@pytest.fixture
def rates(monkeypatch):
    """Tight limits so tests don't need dozens of requests."""
    table = dict(SimpleRateThrottle.THROTTLE_RATES)

    def set_rate(scope, rate):
        table[scope] = rate
        monkeypatch.setattr(SimpleRateThrottle, "THROTTLE_RATES", table)

    return set_rate


def login(client, email, password=WRONG_PASSWORD, ip="10.0.0.1"):
    return client.post(LOGIN, {"email": email, "password": password}, format="json", REMOTE_ADDR=ip)


class TestLoginThrottle:
    def test_blocks_an_address_after_the_limit(self, api_client, rates):
        rates("auth_login", "3/minute")
        for i in range(3):
            assert login(api_client, f"user{i}@x.test").status_code == 401

        response = login(api_client, "someone-else@x.test")

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "throttled"
        assert int(response["Retry-After"]) > 0

    def test_other_addresses_are_unaffected(self, api_client, rates):
        rates("auth_login", "2/minute")
        login(api_client, "a@x.test", ip="10.0.0.1")
        login(api_client, "b@x.test", ip="10.0.0.1")
        assert login(api_client, "c@x.test", ip="10.0.0.1").status_code == 429
        assert login(api_client, "c@x.test", ip="10.0.0.2").status_code == 401

    def test_reads_the_client_ip_through_trusted_proxies(self, api_client, rates, settings):
        rates("auth_login", "1/minute")
        settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}

        def via_ingress(client_ip):
            return api_client.post(
                LOGIN,
                {"email": "a@x.test", "password": WRONG_PASSWORD},
                format="json",
                REMOTE_ADDR="10.244.0.7",  # the ingress pod, same for everyone
                HTTP_X_FORWARDED_FOR=client_ip,
            )

        assert via_ingress("203.0.113.5").status_code == 401
        assert via_ingress("203.0.113.5").status_code == 429
        # A different client behind the same ingress has its own budget.
        assert via_ingress("198.51.100.9").status_code == 401

    def test_blocks_one_account_from_many_addresses(self, api_client, rates):
        rates("auth_login_account", "3/minute")
        for i in range(3):
            login(api_client, "Target@X.test", ip=f"10.0.1.{i}")

        # Same account, new address, different capitalisation: still the same account.
        assert login(api_client, "target@x.test", ip="10.0.2.1").status_code == 429
        assert login(api_client, "bystander@x.test", ip="10.0.2.1").status_code == 401

    def test_counts_successful_logins_too(self, api_client, rates):
        rates("auth_login_account", "2/minute")
        user = UserFactory(email="eng@x.test")
        assert login(api_client, user.email, DEFAULT_PASSWORD).status_code == 200
        assert login(api_client, user.email, DEFAULT_PASSWORD).status_code == 200
        assert login(api_client, user.email, DEFAULT_PASSWORD).status_code == 429

    def test_fails_open_when_the_cache_is_down(self, api_client, rates, monkeypatch):
        rates("auth_login", "1/minute")

        def broken(*args, **kwargs):
            raise ConnectionError("cache down")

        monkeypatch.setattr(
            throttling.FailOpenThrottle, "cache", type("C", (), {"get": broken, "set": broken})()
        )
        for _ in range(3):
            assert login(api_client, "a@x.test").status_code == 401  # never 429, never 500


class TestOtherAuthThrottles:
    def test_refresh_is_limited_per_address(self, api_client, rates):
        rates("auth_refresh", "2/minute")
        for _ in range(2):
            assert api_client.post("/api/v1/auth/token/refresh/").status_code == 401
        assert api_client.post("/api/v1/auth/token/refresh/").status_code == 429

    def test_registration_is_limited_per_address(self, api_client, rates):
        rates("auth_register", "1/hour")
        body = {"email": "new1@x.test", "password": "a-Long-pass-123", "full_name": "N"}
        assert api_client.post("/api/v1/auth/register/", body, format="json").status_code == 201
        body["email"] = "new2@x.test"
        assert api_client.post("/api/v1/auth/register/", body, format="json").status_code == 429

    def test_password_change_is_limited_per_user(self, client_for, engineer, rates):
        rates("auth_password", "1/minute")
        client = client_for(engineer)
        body = {"old_password": "nope", "new_password": "another-Long-pass-1"}
        assert client.post("/api/v1/auth/password/change/", body, format="json").status_code == 400
        assert client.post("/api/v1/auth/password/change/", body, format="json").status_code == 429

    def test_normal_api_calls_are_not_throttled(self, client_for, viewer, rates):
        rates("auth_login", "1/minute")
        client = client_for(viewer)
        for _ in range(5):
            assert client.get("/api/v1/incidents/").status_code == 200


class TestSecurityHeaders:
    def test_api_responses(self, client_for, viewer):
        response = client_for(viewer).get("/api/v1/incidents/")
        assert response["Content-Security-Policy"].startswith("default-src 'none'")
        assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["X-Frame-Options"] == "DENY"
        assert response["Referrer-Policy"] == "same-origin"
        assert response["Cache-Control"] == "no-store"
        assert "camera=()" in response["Permissions-Policy"]

    def test_token_responses_are_never_cached(self, api_client):
        user = UserFactory()
        response = login(api_client, user.email, DEFAULT_PASSWORD)
        assert response.status_code == 200
        assert response["Cache-Control"] == "no-store"

    def test_errors_get_the_headers_too(self, api_client):
        response = api_client.get("/api/v1/incidents/")
        assert response.status_code == 401
        assert response["Cache-Control"] == "no-store"
        assert "Content-Security-Policy" in response

    def test_health_endpoints_are_not_cached(self, api_client):
        assert api_client.get("/health/live")["Cache-Control"] == "no-store"

    def test_docs_page_can_load_its_scripts(self, api_client):
        response = api_client.get("/api/v1/docs/")
        assert "Content-Security-Policy" not in response

    def test_version_header_when_configured(self, api_client, settings):
        settings.APP_VERSION = "1.4.2"
        assert api_client.get("/health/live")["X-OpsDesk-Version"] == "1.4.2"


def test_cache_is_cleared_between_tests():
    assert cache.get("throttle_auth_login_10.0.0.1") is None
