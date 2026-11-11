import os
import time

import pytest
from django.conf import settings

from config.celery import app
from opsdesk_tasks import healthcheck
from opsdesk_tasks.health import HeartbeatScheduler, WorkerHeartbeat


class TestHealthcheck:
    def test_fresh_heartbeat_is_healthy(self, tmp_path):
        f = tmp_path / "hb"
        f.touch()
        assert healthcheck.check(str(f), max_age=60)[0] is True

    def test_stale_heartbeat_is_unhealthy(self, tmp_path):
        f = tmp_path / "hb"
        f.touch()
        old = time.time() - 300
        os.utime(f, (old, old))
        ok, message = healthcheck.check(str(f), max_age=60)
        assert ok is False
        assert "old" in message

    def test_missing_file_is_unhealthy(self, tmp_path):
        assert healthcheck.check(str(tmp_path / "nope"), max_age=60)[0] is False

    def test_cli_exit_codes(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / "hb"
        monkeypatch.setenv("WORKER_HEARTBEAT_FILE", str(f))
        assert healthcheck.main(["worker"]) == 1
        f.touch()
        assert healthcheck.main(["worker", "--max-age", "30"]) == 0
        assert "OK" in capsys.readouterr().out


def test_worker_bootstep_touches_heartbeat_file(tmp_path, settings):
    settings.WORKER_HEARTBEAT_FILE = str(tmp_path / "worker")

    class FakeTimer:
        def call_repeatedly(self, interval, fn, args, priority=0):
            self.interval, self.fn, self.args = interval, fn, args
            return type("T", (), {"cancel": lambda self: None})()

    worker = type("W", (), {"timer": FakeTimer()})()
    step = WorkerHeartbeat(worker)
    step.start(worker)
    assert (tmp_path / "worker").exists()
    assert worker.timer.interval == settings.WORKER_HEARTBEAT_INTERVAL
    step.stop(worker)


def test_beat_scheduler_touches_heartbeat_on_tick(tmp_path, settings, monkeypatch):
    settings.BEAT_HEARTBEAT_FILE = str(tmp_path / "beat")
    monkeypatch.setattr("celery.beat.PersistentScheduler.tick", lambda self, *a, **k: 5)
    scheduler = HeartbeatScheduler.__new__(HeartbeatScheduler)
    assert scheduler.tick() == 5
    assert (tmp_path / "beat").exists()


class TestCeleryConfig:
    def test_queues_and_routes(self):
        assert {q.name for q in app.conf.task_queues} == {"notifications", "sla", "reports"}
        router = app.amqp.router
        assert router.route({}, "notifications.deliver")["queue"].name == "notifications"
        assert router.route({}, "outbox.dispatch_pending")["queue"].name == "notifications"

    def test_reliability_settings(self):
        assert app.conf.task_acks_late is True
        assert app.conf.task_reject_on_worker_lost is True
        assert app.conf.worker_prefetch_multiplier == 1

    def test_outbox_sweep_is_scheduled(self):
        entry = settings.CELERY_BEAT_SCHEDULE["dispatch-outbox"]
        assert entry["task"] == "outbox.dispatch_pending"
        assert entry["task"] in app.tasks

    @pytest.mark.parametrize(
        "name", ["notifications.notify_incident_event", "notifications.deliver"]
    )
    def test_tasks_are_registered(self, name):
        assert name in app.tasks
