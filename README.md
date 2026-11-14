# OpsDesk

An incident management platform: report incidents, assign and work them through a
lifecycle, track response and resolution SLAs, get notified, and see the state of
operations on a dashboard. It is built as independently runnable components so each can be
deployed, scaled and observed on its own.

| Component | Path | Process | Replicas |
| --- | --- | --- | --- |
| Frontend | `frontend/` | React + TypeScript + Tailwind SPA, static files | Any |
| API | `backend/` | Django REST Framework under gunicorn | Any (stateless) |
| Worker | `backend/` | `celery -A config worker` (queues: notifications, sla, reports) | Any, per queue |
| Scheduler | `backend/` | `celery -A config beat` | Exactly one |

The components share only PostgreSQL and Redis. The frontend talks to the API only through
`/api/v1/`. Configuration comes entirely from environment variables, documented in
[`backend/.env.example`](backend/.env.example) and [`frontend/.env.example`](frontend/.env.example).

Kubernetes manifests for deploying every component are in [`k8s/`](k8s/), and the problems I
hit deploying them are written up in [docs/kubernetes-troubleshooting.md](docs/kubernetes-troubleshooting.md).

## Features

- Sign-in with JWT access tokens and rotating, revocable refresh tokens in an httpOnly cookie
- Roles: Admin, Engineer and Viewer, enforced by the API
- Incidents: priorities, statuses with enforced transitions, assignment, comments, full
  activity history, search, filters and pagination
- SLA targets per priority, at-risk and breach detection, and reminders
- In-app and email notifications
- Daily, weekly and on-demand reports
- Dashboard with live counts, trends and per-engineer workload
- Health endpoints for the API and heartbeat checks for the worker and scheduler
- Rate-limited sign-in, and security headers on every response

## Quick start (local)

Needs Python 3.12+, Node 20+, PostgreSQL 14+ and Redis 6+ running locally.

```bash
# API
cd backend
python -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env                       # then edit the placeholder secrets
export DJANGO_SETTINGS_MODULE=config.settings.dev
python manage.py migrate
python manage.py createsuperuser           # becomes an Admin
python manage.py runserver                 # http://localhost:8000

# Worker and scheduler (two more terminals, same venv and env)
celery -A config worker -Q notifications,sla,reports -l info
celery -A config beat -l info

# Frontend
cd frontend
npm install
npm run dev                                # http://localhost:5173
```

## Tests

```bash
cd backend && pytest          # 270 tests against a real PostgreSQL; Redis is faked
cd frontend && npm test       # 72 tests with Vitest, Testing Library and MSW
```

## Documentation

| Document | Covers |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Components, request path, scaling, failure behaviour, health checks, security, configuration |
| [docs/database.md](docs/database.md) | Tables, constraints, indexes, the incident lifecycle and how concurrency is handled |
| [docs/api.md](docs/api.md) | Conventions, error envelope, authentication, endpoints and the permission matrix |
| [docs/background-processing.md](docs/background-processing.md) | Queues, tasks, the transactional outbox, retries, idempotency and liveness |
| [docs/kubernetes-troubleshooting.md](docs/kubernetes-troubleshooting.md) | Problems hit deploying to Kubernetes and how `kubectl logs` and `describe` found them |
| [backend/README.md](backend/README.md) | Running and testing the API, worker and scheduler |
| [frontend/README.md](frontend/README.md) | Running, configuring and testing the SPA |
