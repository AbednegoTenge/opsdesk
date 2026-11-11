import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";

import type { Role, User } from "@/api/types";

import { byAssignee, summary, trends } from "./fixtures";

export const API = "http://localhost:3000/api/v1";

export function makeUser(role: Role = "engineer", overrides: Partial<User> = {}): User {
  return {
    id: 1,
    email: `${role}@opsdesk.test`,
    full_name: `Test ${role}`,
    role,
    is_active: true,
    date_joined: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/**
 * A tiny fake of the API's auth behaviour. `refreshUser` stands in for the httpOnly
 * refresh cookie: when set, POST /auth/token/refresh/ succeeds for that user.
 */
export const backend = {
  refreshUser: null as User | null,
  refreshCalls: 0,
  logoutCalls: 0,
  tokenCounter: 0,
  validTokens: new Set<string>(),
  password: "correct-horse",
  refreshStatus: null as number | null,
};

export function resetBackend() {
  backend.refreshUser = null;
  backend.refreshCalls = 0;
  backend.logoutCalls = 0;
  backend.tokenCounter = 0;
  backend.validTokens.clear();
  backend.refreshStatus = null;
}

export function issueToken(): string {
  backend.tokenCounter += 1;
  const token = `access-${backend.tokenCounter}`;
  backend.validTokens.add(token);
  return token;
}

/** Simulate the access token expiring: every token issued so far stops working. */
export function expireAccessTokens() {
  backend.validTokens.clear();
}

export function errorBody(code: string, message: string, details: unknown = null) {
  return { error: { code, message, details } };
}

function bearerIsValid(request: Request): boolean {
  const header = request.headers.get("Authorization") ?? "";
  return backend.validTokens.has(header.replace(/^Bearer /, ""));
}

export const handlers = [
  http.post(`${API}/auth/token/`, async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    if (body.password !== backend.password) {
      return HttpResponse.json(errorBody("invalid_login", "Invalid email or password."), {
        status: 401,
      });
    }
    const role = (body.email.split("@")[0] as Role) || "engineer";
    const user = makeUser(["admin", "engineer", "viewer"].includes(role) ? role : "engineer", {
      email: body.email,
    });
    backend.refreshUser = user;
    return HttpResponse.json({ access: issueToken(), user });
  }),

  http.post(`${API}/auth/token/refresh/`, () => {
    backend.refreshCalls += 1;
    if (backend.refreshStatus) {
      return HttpResponse.json(errorBody("service_unavailable", "Auth store unavailable."), {
        status: backend.refreshStatus,
      });
    }
    if (!backend.refreshUser) {
      return HttpResponse.json(errorBody("no_refresh_token", "No refresh token provided."), {
        status: 401,
      });
    }
    return HttpResponse.json({ access: issueToken(), user: backend.refreshUser });
  }),

  http.post(`${API}/auth/logout/`, () => {
    backend.logoutCalls += 1;
    backend.refreshUser = null;
    return new HttpResponse(null, { status: 204 });
  }),

  http.get(`${API}/auth/me/`, ({ request }) => {
    if (!bearerIsValid(request)) {
      return HttpResponse.json(errorBody("token_not_valid", "Token is invalid or expired."), {
        status: 401,
      });
    }
    return HttpResponse.json(backend.refreshUser);
  }),
];

// Defaults for what every signed-in page loads: the unread count in the header and the
// dashboard (the landing page). Tests override these with server.use().
handlers.push(
  http.get(`${API}/notifications/unread-count/`, () => HttpResponse.json({ unread: 0 })),
  http.get(`${API}/dashboard/summary/`, () => HttpResponse.json(summary)),
  http.get(`${API}/dashboard/by-assignee/`, () => HttpResponse.json(byAssignee)),
  http.get(`${API}/dashboard/trends/`, () => HttpResponse.json(trends)),
);

export const server = setupServer(...handlers);
