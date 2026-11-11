# OpsDesk

Incident management platform built as independently runnable components:

| Component | Path | Process | Status |
| --- | --- | --- | --- |
| Backend API | `backend/` | Django REST Framework under any WSGI server | Milestones 1 to 4 done |
| Background worker | `backend/` | `celery -A config worker` | Milestone 3 done |
| Scheduler | `backend/` | `celery -A config beat` (exactly one replica) | Milestone 4 done |
| Frontend | `frontend/` | React SPA, static files | Milestone 6 |

The components share only PostgreSQL and Redis, and the frontend talks to the API only through
`/api/v1/`. Containerization, infrastructure and deployment are intentionally out of scope for
this repository's application code.

See [backend/README.md](backend/README.md) to run the API and its tests, and `docs/` for the
architecture, database, API and background-processing design.
