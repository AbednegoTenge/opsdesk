# OpsDesk backend

Django REST API (and, from milestone 3, the Celery worker and Beat processes) for OpsDesk.

## What is here (milestones 1 and 2)

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

## Tests

Tests use a real PostgreSQL database (they rely on its transaction behaviour) and an in-memory
fake Redis, so only PostgreSQL needs to be running.

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
