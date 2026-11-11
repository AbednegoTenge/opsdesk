# API

REST over JSON, versioned under `/api/v1/`. Interactive docs are served by the API at
`/api/v1/docs/` and the OpenAPI schema at `/api/v1/schema/`. A snapshot of the schema lives
in [`frontend/openapi.yaml`](../frontend/openapi.yaml), from which the frontend's types are
generated.

## Conventions

- **Authentication:** `Authorization: Bearer <access token>` on every endpoint except
  sign-in, refresh, sign-out, registration and health.
- **Requests and responses are JSON.** Timestamps are ISO 8601 in UTC.
- **Pagination:** list endpoints return
  `{"count", "next", "previous", "results"}`. Use `?page=` and `?page_size=` (default 25,
  maximum 100).
- **Errors** always use one envelope:

  ```json
  {"error": {"code": "validation_error", "message": "Request validation failed.",
             "details": {"priority": ["\"urgent\" is not a valid choice."]}}}
  ```

  | Status | Typical `code` | Meaning |
  | --- | --- | --- |
  | 400 | `validation_error` | Bad input, or a business rule refused the change (e.g. an invalid status move). `details` holds the reasons by field. |
  | 401 | `not_authenticated`, `token_not_valid`, `invalid_login`, `token_revoked` | Missing, expired or revoked credentials |
  | 403 | `permission_denied` | Authenticated but not allowed (role, or e.g. reopening a closed incident as a non-Admin) |
  | 404 | `not_found` | |
  | 429 | `throttled` | Rate limit hit; wait `Retry-After` seconds |
  | 503 | `service_unavailable` | A dependency (Redis for auth endpoints) is down; retry |

- **Unknown filter values are rejected** with 400 instead of being silently ignored.

## Authentication

| Method and path | Body | Result |
| --- | --- | --- |
| `POST /auth/token/` | `{email, password}` | `200 {access, user}` and the refresh cookie |
| `POST /auth/token/refresh/` | none (cookie) or `{refresh}` | `200 {access, user}` and a new cookie; the old refresh token stops working |
| `POST /auth/logout/` | none (cookie) | `204`; revokes the refresh token and clears the cookie |
| `POST /auth/register/` | `{email, full_name, password}` | `201 user` as a Viewer (if `ALLOW_REGISTRATION`) |
| `GET /auth/me/`, `PATCH /auth/me/` | `{full_name}` | The current user |
| `POST /auth/password/change/` | `{old_password, new_password}` | `204`; signs the user out everywhere |

- **Access token:** a JWT valid for `JWT_ACCESS_TTL_MINUTES` (15). Its claims carry the user
  id, issuer and audience.
- **Refresh cookie:** `opsdesk_refresh`, httpOnly, scoped to `/api/v1/auth/`. It is valid for
  `JWT_REFRESH_TTL_DAYS` (7) and is tracked in Redis.

**Rate limits**, configurable through `THROTTLE_*` variables:

| Endpoint | Limit |
| --- | --- |
| Sign-in | 20/min per IP and 10/min per account |
| Refresh | 120/min per IP |
| Registration | 10/hour per IP |
| Password change | 5/min per user |

## Endpoints

| Method and path | Purpose |
| --- | --- |
| `GET /incidents/` | List. Filters: `search`, `status`, `priority`, `sla_status` (each comma-separated), `assignee` (`<id>`, `me`, `none`), `reporter`, `created_after`, `created_before`, `ordering` (`created_at`, `updated_at`, `priority`, `resolve_due_at`, each optionally prefixed with `-`) |
| `POST /incidents/` | Create: `{title, description?, priority, assignee_id?}` |
| `GET /incidents/{id}/` | Detail, including due times and lifecycle timestamps |
| `PATCH /incidents/{id}/` | Edit `title`, `description`, `priority` (priority recomputes due times) |
| `DELETE /incidents/{id}/` | Delete with comments and history |
| `POST /incidents/{id}/assign/` | `{assignee_id}` (null to unassign); only active Engineers and Admins can be assigned |
| `POST /incidents/{id}/transition/` | `{status, note?}`. Allowed moves are open → in progress or resolved, in progress → resolved, resolved → closed or in progress, closed → in progress (Admin only). Starting work on an unassigned incident assigns it to the caller. |
| `GET, POST /incidents/{id}/comments/` | List, add `{body}` |
| `PATCH, DELETE /incidents/{id}/comments/{comment_id}/` | Edit or delete (author or Admin) |
| `GET /incidents/{id}/events/` | Activity history, oldest first |
| `GET /sla-policies/` | Targets per priority |
| `PATCH /sla-policies/{priority}/` | Change `response_minutes`, `resolution_minutes`, `reminder_interval_minutes` |
| `GET /dashboard/summary/` | Totals by status, active by priority, critical, unassigned, SLA breached / at risk |
| `GET /dashboard/by-assignee/?days=30` | Active, in-progress, critical and breached counts, plus resolved in the window, per engineer |
| `GET /dashboard/trends/?days=30` | Daily created / resolved / SLA breaches, totals, mean time to resolve (`days` 1 to 365) |
| `GET /notifications/?unread=true` | Your notifications |
| `GET /notifications/unread-count/` | `{unread}` |
| `POST /notifications/mark-read/` | `{ids: [...]}` or `{all: true}` |
| `GET /reports/`, `GET /reports/{id}/` | Generated reports; detail includes the figures |
| `POST /reports/` | `{period_start, period_end}` (at most 366 days). Returns `202` with a pending report, or `200` if that exact period already has one. |
| `GET /users/` | Users. Filters: `search`, `role`, `is_active` |
| `GET, PATCH /users/{id}/` | Change `full_name`, `role`, `is_active`; changing role or active status revokes the user's sessions. Admins can't demote or deactivate themselves. |

Health endpoints sit outside `/api/v1/`: `GET /health/live` and `GET /health/ready`. See
[architecture.md](architecture.md#health-checks).

## Permissions

| Action | Viewer | Engineer | Admin |
| --- | --- | --- | --- |
| Read incidents, comments, history, SLA policies, dashboard | yes | yes | yes |
| Own notifications, profile, password | yes | yes | yes |
| Create, edit, assign, transition incidents; comment | | yes | yes |
| Edit or delete own comments | | yes | yes |
| Edit or delete anyone's comments | | | yes |
| Reopen a closed incident | | | yes |
| Delete incidents | | | yes |
| List users (to pick an assignee) | | yes | yes |
| Change users' roles or status | | | yes |
| Read reports | | yes | yes |
| Request a report | | | yes |
| Change SLA policies | | | yes |

## Versioning

Breaking changes go to a new prefix (`/api/v2/`) served alongside v1 until clients move.
Adding fields, endpoints or optional parameters is not breaking, and clients should ignore
fields they don't know.
