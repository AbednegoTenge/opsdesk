# OpsDesk backend

Django REST API (and, from milestone 3, the Celery worker and Beat processes) for OpsDesk.

## What is here (milestones 1 to 4)

| Area | Where |
| --- | --- |
| Settings, all from environment variables | `config/settings/{base,dev,test,prod}.py` |
| Custom user with roles (Admin, Engineer, Viewer) | `apps/users/models.py` |
| JWT auth, refresh tokens tracked in Redis | `apps/users/views.py`, `apps/users/token_store.py` |
| Role permission classes | `apps/core/permissions.py` |
| Health checks | `apps/core/health.py` |
| Error envelope, pagination, JSON logging | `apps/core/` |
| Incidents, comments, activity history, SLA policies | `apps/incidents/models.py` |
| Incident business rules (one transaction per change) | `apps/incidents/services.py` |
| Incident endpoints, search and filters | `apps/incidents/views.py`, `apps/incidents/filters.py` |
| Celery app, queues, routes, Beat schedule | `config/celery.py`, `CELERY_*` in `config/settings/base.py` |
| Base task (retries, backoff, logging), outbox, worker/Beat health | `opsdesk_tasks/` |
| Notification tasks, channels, in-app notifications API | `apps/notifications/` |
| SLA monitor and reminders | `apps/sla/` |
| Incident summary reports and reports API | `apps/reporting/` |

## Incident rules

* Every change goes through `apps/incidents/services.py`, which locks the incident row and writes
  the matching `IncidentEvent` in the same transaction. If either write fails, both roll back.
* Status moves: Open to In Progress or Resolved; In Progress to Resolved; Resolved to Closed or
  back to In Progress; Closed to In Progress (Admins only). Anything else is a 400.
* Starting work on an unassigned incident assigns it to whoever started it.
* Status and assignee change only through `POST /incidents/{id}/transition/` and
  `POST /incidents/{id}/assign/`; `PATCH` edits title, description and priority.
* SLA due times come from `SLAPolicy` (seeded with defaults: Critical 15 min / 4 h, High 1 h / 8 h,
  Medium 4 h / 24 h, Low 24 h / 72 h) and are recomputed from the creation time if priority changes.
* List filters: `search`, `status`, `priority`, `sla_status` (comma-separated), `assignee`
  (id, `me` or `none`), `reporter`, `created_after`, `created_before`, `ordering`
  (`created_at`, `updated_at`, `priority`, `resolve_due_at`, each optionally prefixed with `-`).

## Requirements

* Python 3.12+
* PostgreSQL 14+
* Redis 6.2+ (uses `GETDEL`)

Dependencies are split per process:

| File | Used by |
| --- | --- |
| `requirements/base.txt` | everything |
| `requirements/api.txt` | API process |
| `requirements/worker.txt` | Celery worker and Beat |
| `requirements/dev.txt` | local development and tests |

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env            # then edit values
python manage.py migrate
python manage.py createsuperuser  # creates an Admin
python manage.py runserver
```

`manage.py` defaults to `config.settings.dev`, which reads `backend/.env`. Production uses
`config.settings.prod` (the default in `config/wsgi.py`) and reads only real environment variables.

Run the API in production mode with any WSGI server, for example:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

Migrations are a separate one-off step (`python manage.py migrate`), never run at API startup,
so replicas can start in parallel.

## Background processing

Three processes run from this same codebase, each started on its own:

```bash
# API (any number of replicas)
gunicorn config.wsgi:application --bind 0.0.0.0:8000
# Worker (any number of replicas; can be split per queue)
celery -A config worker -Q notifications,sla,reports --loglevel=INFO
# Scheduler (exactly ONE replica, or periodic tasks run twice)
celery -A config beat --loglevel=INFO
```

`config/celery.py` defaults to `config.settings.prod`; for local runs export
`DJANGO_SETTINGS_MODULE=config.settings.dev` first.

How a notification flows:

1. A service call (for example assigning an incident) writes the incident, its `IncidentEvent`
   and an `OutboxMessage`, all in one transaction.
2. After commit, the outbox row is published to Redis. If Redis is down the request still
   succeeds, the row stays `pending`, and the `outbox.dispatch_pending` sweep (Beat, every
   minute) publishes it once Redis is back.
3. `notifications.notify_incident_event` creates one `NotificationDelivery` per recipient and
   channel (in-app and email). Each has a unique `dedupe_key`, so running the task twice
   creates nothing new.
4. `notifications.deliver` locks its row (`FOR UPDATE NOWAIT`), skips rows already sent, and
   sends. Transient errors (database, Redis, SMTP connection) retry with exponential backoff and
   jitter, up to `TASK_MAX_RETRIES`; permanent errors and bugs fail at once. A delivery that
   runs out of retries is marked `failed` with the last error.

Who is notified: Admins about new incidents, the assignee when assigned, the assignee and
reporter when priority changes. The person who made the change is never notified.

Tasks use `acks_late` and `reject_on_worker_lost`, so a worker killed mid-task has its task
redelivered; the dedupe rules make that redelivery harmless.

Worker and Beat health: each touches a heartbeat file on a timer. Probe it with

```bash
python -m opsdesk_tasks.healthcheck worker --max-age 60   # exit 0 healthy, 1 not
python -m opsdesk_tasks.healthcheck beat --max-age 60
```

This catches a process that is alive but stuck, not just one that has exited.

### Scheduled work (Celery Beat)

| Task | Default schedule | Queue | What it does | Why it never doubles up |
| --- | --- | --- | --- | --- |
| `outbox.dispatch_pending` | every 60 s | notifications | publishes tasks that missed their on-commit publish | `SKIP LOCKED` row claim |
| `sla.check_breaches` | every 60 s | sla | flags open incidents past their response or resolution target, records an `sla_breached` event, notifies the assignee and Admins; marks incidents 75% through their resolution window as `at_risk` | conditional `UPDATE ... WHERE <target>_breached_at IS NULL`; only the run that changed the row writes the event |
| `sla.send_reminders` | every 5 min | sla | reminds the assignee (or Admins if unassigned) about unresolved incidents whose priority has a reminder interval (Critical 30 min, High 60 min by default) | conditional `UPDATE` of `last_reminded_at`; at most one reminder per incident per interval |
| `reporting.schedule_periodic_report` | daily and Monday at `REPORT_HOUR_UTC` | reports | creates the report for the previous day or week and queues generation; emails Admins a summary | unique `(kind, period_start, period_end)`; a rerun returns the existing report |

The response target is met when the incident is first acknowledged (moved to In Progress or
Resolved). A breach stays on the record after the incident is resolved.

On-demand reports: `POST /api/v1/reports/` (Admin) with `period_start` and `period_end` returns
`202` immediately with the report id; a worker fills it in and `GET /api/v1/reports/{id}/`
shows `status: completed` and the data. Asking for the same period again returns the same report.

For local debugging without a worker, `CELERY_TASK_ALWAYS_EAGER=true` runs tasks inline.

## Tests

Tests use a real PostgreSQL database (they rely on its transaction behaviour) and an in-memory
fake Redis. Celery runs in eager mode with an in-memory broker, and tests use
`django_capture_on_commit_callbacks` to check that tasks are published only after commit. Only
PostgreSQL needs to be running.

```bash
cd backend
source .venv/bin/activate
# DATABASE_URL defaults to postgres://opsdesk:opsdesk@localhost:5432/opsdesk;
# the user needs CREATEDB so pytest can create the test database.
pytest
pytest tests/api/test_auth.py -k refresh   # a subset
ruff check . && ruff format --check .
```

## Auth model

* `POST /api/v1/auth/token/` with email and password returns `{access, user}` and sets the
  refresh token as an httpOnly cookie scoped to `/api/v1/auth/`. JavaScript never sees it.
* Access tokens last 15 minutes. Send them as `Authorization: Bearer <token>`.
* `POST /api/v1/auth/token/refresh/` consumes the refresh token and issues a new pair
  (rotation). Each refresh token works once: it is stored in Redis under its `jti` and deleted
  with an atomic `GETDEL`. A reused or revoked token gets 401 `token_revoked`. Clients should
  not fire two refreshes at once, because the second one will fail.
* `POST /api/v1/auth/logout/` revokes the current refresh token.
* Changing a password, or an Admin changing someone's role or deactivating them, revokes all of
  that user's refresh tokens. Their current access token lasts at most 15 more minutes (and
  stops at once if the user is deactivated).
* If Redis is down, login, refresh and logout return 503. Requests with a valid access token keep
  working because verification needs only the shared `JWT_SIGNING_KEY`.

## Health checks

| Path | Meaning | Fails when |
| --- | --- | --- |
| `GET /health/live` | process is up | never, if the process answers |
| `GET /health/ready` | can serve traffic | PostgreSQL does not answer `SELECT 1` within `HEALTH_DB_TIMEOUT_MS` |

`/health/ready` also reports Redis, but does not fail on it (see the auth notes above).

## API docs

OpenAPI schema at `/api/v1/schema/`, Swagger UI at `/api/v1/docs/`.
