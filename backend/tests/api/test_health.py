import pytest
from django.db import OperationalError, connection


def test_live_needs_no_dependencies(client):
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_when_database_is_up(client):
    res = client.get("/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["ok"] is True
    assert body["checks"]["redis"]["ok"] is True


@pytest.mark.django_db
def test_not_ready_when_database_fails(client, monkeypatch):
    def broken_cursor(*args, **kwargs):
        raise OperationalError("connection refused")

    monkeypatch.setattr(connection, "cursor", broken_cursor)
    res = client.get("/health/ready")
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"] == {"ok": False, "error": "OperationalError"}


@pytest.mark.django_db
def test_still_ready_when_only_redis_is_down(client, redis_down):
    res = client.get("/health/ready")
    assert res.status_code == 200
    assert res.json()["checks"]["redis"]["ok"] is False


def test_health_endpoints_need_no_auth_and_are_get_only(client):
    assert client.post("/health/live").status_code == 405
