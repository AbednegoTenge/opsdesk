# OpsDesk frontend

React 18 + TypeScript + Tailwind single-page app, built with Vite. It talks to the API only
through `/api/v1/` and builds to plain static files (`dist/`) that any static file server can
host.

## Run it

```bash
cd frontend
npm install
cp .env.example .env.local     # optional; defaults work with the API on localhost:8000
npm run dev                    # http://localhost:5173
```

Start the API first (see `backend/README.md`). The dev server forwards `/api` to
`VITE_DEV_API_PROXY_TARGET`, so the browser sees one origin and no CORS setup is needed.

| Command | What it does |
| --- | --- |
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Type-check, then build static files into `dist/` |
| `npm run preview` | Serve `dist/` locally |
| `npm test` | Vitest + React Testing Library + MSW |
| `npm run lint` / `npm run typecheck` | ESLint / `tsc` |
| `npm run api:types` | Regenerate `src/api/schema.d.ts` from `openapi.yaml` |

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api/v1` | API base URL, compiled into the bundle |
| `VITE_DEV_API_PROXY_TARGET` | `http://localhost:8000` | Dev server only: where `/api` is forwarded |

`VITE_*` values are baked in at build time and are public. To run **one build in many
environments**, serve a different `config.js` next to `index.html` instead of rebuilding:

```js
window.__OPSDESK_CONFIG__ = { apiBaseUrl: "https://api.staging.example.com/api/v1" };
```

Runtime config wins over the build-time value. Keep the default relative `/api/v1` when the
app and API are served from the same host, which is what the refresh cookie expects. If the API
is on another origin, add this app's origin to the API's `CORS_ALLOWED_ORIGINS`.

## How sign-in works

- **Login** (`POST /auth/token/`) returns a short-lived access token in the body and sets the
  refresh token as an httpOnly cookie scoped to `/api/v1/auth/`.
- **The access token lives only in memory** (`src/api/session.ts`), never in localStorage, so
  injected scripts can't lift a long-lived credential.
- **On page load** the app calls `POST /auth/token/refresh/`; the browser sends the cookie and
  the session comes back without a new login.
- **On a 401** the API client (`src/api/client.ts`) refreshes once and retries. Concurrent
  requests share one refresh, and tabs take turns through a Web Lock, because the API rotates
  the refresh token on every use and treats a second use as reuse.
- **If the auth service is down** (503 or no connection), the app shows a "try again" screen
  instead of signing the user out.
- **Logout** revokes the refresh token in Redis and clears the cookie and in-memory state.

## Roles in the UI

`src/components/navigation.ts` hides links a role can't use, and `RequireRole` routes show a
403 page. This is convenience only: the API enforces every permission.

| Page | Viewer | Engineer | Admin |
| --- | --- | --- | --- |
| Dashboard, Incidents | yes | yes | yes |
| Reports | | yes | yes |
| Users, SLA policies | | | yes |

## API types

`openapi.yaml` is a snapshot of the API schema. After changing the API, refresh it and the
generated types:

```bash
cd backend && python manage.py spectacular --file ../frontend/openapi.yaml --validate
cd ../frontend && npm run api:types
```

## Layout

```
src/
  api/          client (fetch + refresh), errors, session, generated schema types
  auth/         AuthProvider, useAuth, route guards, role helpers
  components/   layout, navigation, shared UI
  pages/        route screens
  test/         MSW fake API, test setup, render helper
```
