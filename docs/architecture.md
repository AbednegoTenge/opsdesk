# Architecture

The full design (diagrams, ERD, endpoint list, task flows and milestones) was reviewed and
approved as "OpsDesk Design (Phase 0)". This file and the other `docs/` files are filled in
milestone 8 from that design and from what was actually built.

Summary:

* **Frontend**: React + TypeScript + Tailwind SPA, served as static files, talks to `/api/v1/`.
* **API**: stateless Django REST Framework process; any number of replicas.
* **Worker**: Celery worker processes consuming the `notifications`, `sla` and `reports` queues.
* **Beat**: one Celery Beat process scheduling periodic tasks.
* **PostgreSQL**: all application data.
* **Redis**: Celery broker and refresh-token store.
