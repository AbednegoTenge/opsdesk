# Background processing

Everything slow or unreliable (email, SLA checks, reminders, reports) runs in Celery
workers, never in an API request. Celery Beat publishes the periodic tasks. Redis is the
broker; PostgreSQL holds every piece of state the tasks read or write.

## Processes

```bash
# Worker: any number of replicas. Consume all queues, or run one deployment per queue.
celery -A config worker -Q notifications,sla,reports --concurrency 4

# Scheduler: exactly one replica.
celery -A config beat

# Liveness checks for each (exit code 0 = healthy)
python -m opsdesk_tasks.healthcheck worker --max-age 60
python -m opsdesk_tasks.healthcheck beat --max-age 120
```

`config/celery.py` defaults to `config.settings.prod`; export
`DJANGO_SETTINGS_MODULE=config.settings.dev` for local runs. Both need the same environment as the API (`DJANGO_SETTINGS_MODULE`, `DATABASE_URL`,
`REDIS_URL`, `CELERY_BROKER_URL`, …). Install `requirements/worker.txt`; it has no web server.

## Queues and routing

| Queue | Tasks (routed by name prefix in `config/celery.py`) | Why separate |
| --- | --- | --- |
| `notifications` | `notifications.*`, `outbox.*` | Many small, latency-sensitive tasks |
| `sla` | `sla.*` | Must keep running on time even when other queues are backed up |
| `reports` | `reporting.*` | Few, slow, heavier queries; isolated so they can't delay alerts |

Splitting queues lets you scale them independently, e.g. two replicas on `notifications`
and one on `reports`.

## Tasks

| Task | Trigger | What it does |
| --- | --- | --- |
| `notifications.notify_incident_event` | Outbox, after an incident change commits | Works out recipients for the event, creates one `NotificationDelivery` per recipient and channel, and queues each |
| `notifications.deliver` | Queued by the task above | Sends one delivery: an in-app `Notification` row or an email |
| `outbox.dispatch_pending` | Beat, every `OUTBOX_SWEEP_INTERVAL_SECONDS` (60) | Re-publishes outbox rows still pending after `OUTBOX_RETRY_AFTER_SECONDS` |
| `sla.check_breaches` | Beat, every `SLA_CHECK_INTERVAL_SECONDS` (60) | Updates `sla_status` (at risk at 75% of a window) and flags response and resolution breaches once each |
| `sla.send_reminders` | Beat, every `REMINDER_CHECK_INTERVAL_SECONDS` (300) | Reminds about active incidents whose priority has a reminder interval, at most once per interval |
| `reporting.schedule_periodic_report` | Beat, daily at `REPORT_HOUR_UTC`, weekly on Mondays | Creates the report row for the previous day or week (once) and queues generation |
| `reporting.generate_report` | Queued by the task above, or by `POST /reports/` | Computes the figures, marks the report complete, emails the Admins |

Who is notified:

| Event | Recipients (never the person who made the change) |
| --- | --- |
| Incident created | Admins |
| Assigned | The new assignee |
| Priority changed | Assignee and reporter |
| SLA breached | Assignee and every Admin |
| Reminder | Assignee, or the Admins if nobody owns it |
| Report ready | Admins (email) |

## The outbox

A task published straight from a request has two failure modes: published before the
transaction commits (the worker reads data that may still roll back), or lost if the broker
is down. OpsDesk avoids both with a transactional outbox.

```mermaid
sequenceDiagram
    participant API
    participant PG as PostgreSQL
    participant R as Redis broker
    participant B as Beat
    participant W as Worker

    API->>PG: BEGIN; update incident; insert IncidentEvent; insert OutboxMessage
    API->>PG: COMMIT
    API-)R: on_commit: publish task, mark row sent
    Note over API,R: If Redis is down, the row stays pending and the request still succeeds
    B->>R: every 60 s: outbox.dispatch_pending
    R->>W: dispatch_pending
    W->>PG: SELECT pending rows FOR UPDATE SKIP LOCKED
    W-)R: re-publish each, mark sent
    R->>W: notify_incident_event
```

`opsdesk_tasks.outbox.enqueue()` refuses to run outside a transaction, so the "publish after
commit" guarantee can't be skipped by accident.

## Retries

Every task uses the base class `opsdesk_tasks.base.OpsDeskTask`:

- **Transient errors are retried automatically**: database connection errors, Redis
  connection or timeout errors, SMTP disconnects, socket timeouts, and `TransientTaskError`
  raised by a task.
- **Exponential backoff with jitter**: 2 s, 4 s, 8 s, … capped at `TASK_RETRY_BACKOFF_MAX`
  (600 s), for at most `TASK_MAX_RETRIES` (5) attempts.
- **Permanent errors are not retried.** For example, an email address the server rejects
  marks that delivery `failed` at once.
- **Every retry and failure is logged** as JSON with the task name, id and arguments.

Worker settings that make retries safe:

| Setting | Value | Effect |
| --- | --- | --- |
| `task_acks_late` | true | A task is acknowledged after it finishes, so a crash mid-task means redelivery |
| `task_reject_on_worker_lost` | true | A killed worker process puts its task back on the queue |
| `worker_prefetch_multiplier` | 1 | A worker holds only the task it's running, so a crash strands nothing else |
| `broker_transport_options.visibility_timeout` | `CELERY_VISIBILITY_TIMEOUT` (3600 s) | Must exceed the longest task plus its retry delay, or Redis redelivers a running task |
| Time limits | per task (e.g. SLA check 60 s, reports 300 s) | A hung task is killed and retried instead of blocking a worker |

## Idempotency: no duplicate side effects

At-least-once delivery means any task can run twice: redelivery after a crash, the outbox
sweep re-publishing a message whose first publish actually succeeded, or two Beat instances
overlapping during a restart. Every task is written so a second run changes nothing.

| Task | Mechanism |
| --- | --- |
| `notify_incident_event` | `NotificationDelivery.dedupe_key` is unique (`event:{id}:user:{uid}:{channel}`); `get_or_create` returns the existing row on a rerun |
| `deliver` | Locks its row with `SELECT … FOR UPDATE NOWAIT`. If another worker holds it, this run returns `busy`. Deliveries already `sent`, `failed` or `skipped` are skipped. |
| `check_breaches` | `UPDATE incident SET response_breached_at = now WHERE id = … AND response_breached_at IS NULL`. Only the run that changes the row records the event and notifies. |
| `send_reminders` | Claims each reminder by moving `last_reminded_at` in a conditional `UPDATE`; a concurrent run's update matches no rows |
| `schedule_periodic_report` | Unique (`kind`, `period_start`, `period_end`): the second attempt finds the existing report |
| `generate_report` | Locks the report with `SKIP LOCKED` and returns early if already `completed` |
| `dispatch_pending` | `SKIP LOCKED` so concurrent sweeps take different rows |

The test suite exercises each of these by running tasks twice, concurrently, and with
injected failures (`backend/tests/tasks/`).

## Liveness

Celery has no HTTP port, so each process proves it's alive through a file:

- **Worker**: a bootstep (`opsdesk_tasks.health.WorkerHeartbeat`) touches
  `WORKER_HEARTBEAT_FILE` every `WORKER_HEARTBEAT_INTERVAL` seconds from inside the worker's
  event loop. A hung or deadlocked worker stops touching it.
- **Beat**: a custom scheduler touches `BEAT_HEARTBEAT_FILE` on every tick.
- `python -m opsdesk_tasks.healthcheck worker|beat --max-age N` exits 1 when the file is
  older than N seconds. Use it as the liveness probe.

## Observability

All processes log one JSON object per line (`LOG_FORMAT=json`) to stdout, including task
name, task id, attempt and error on every retry or failure. Useful signals to alert on:

- outbox rows `pending` for more than a few minutes, which means the broker or Beat is down
- `notifications_notificationdelivery` rows in `failed`
- reports stuck in `pending`
- heartbeat checks failing
