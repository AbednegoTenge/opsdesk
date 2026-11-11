import fakeredis
import pytest
import redis
from rest_framework.test import APIClient

from apps.users import token_store
from apps.users.models import Role

from .factories import DEFAULT_PASSWORD, UserFactory


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Every test gets an isolated in-memory Redis instead of a real server."""
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setattr("apps.users.token_store.get_redis", lambda: client)
    monkeypatch.setattr("apps.core.health.get_redis", lambda: client)
    return client


@pytest.fixture
def redis_down(monkeypatch):
    """Simulate Redis being unreachable."""

    class Broken:
        def __getattr__(self, name):
            def fail(*args, **kwargs):
                raise redis.ConnectionError("Redis is down")

            return fail

    broken = Broken()
    monkeypatch.setattr("apps.users.token_store.get_redis", lambda: broken)
    monkeypatch.setattr("apps.core.health.get_redis", lambda: broken)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def password():
    return DEFAULT_PASSWORD


@pytest.fixture
def admin(db):
    return UserFactory(role=Role.ADMIN, email="admin@example.com")


@pytest.fixture
def engineer(db):
    return UserFactory(role=Role.ENGINEER, email="engineer@example.com")


@pytest.fixture
def viewer(db):
    return UserFactory(role=Role.VIEWER, email="viewer@example.com")


@pytest.fixture
def client_for():
    """APIClient authenticated with a real access token for the given user."""

    def make(user):
        client = APIClient()
        refresh = token_store.issue_for(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        return client

    return make
