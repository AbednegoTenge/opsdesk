import { apiBaseUrl } from "@/config";

import { ApiError, NetworkError, errorFromResponse } from "./errors";
import { session, type Session } from "./session";
import type { AuthResponse } from "./types";

type Json = Record<string, unknown> | unknown[];

export type RequestOptions = Omit<RequestInit, "body"> & {
  body?: Json;
  query?: Record<string, string | number | boolean | undefined | null>;
};

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = `${apiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

async function send(path: string, options: RequestOptions, accessToken?: string) {
  const { body, query, headers, ...init } = options;
  const finalHeaders = new Headers(headers);
  finalHeaders.set("Accept", "application/json");
  if (body !== undefined) finalHeaders.set("Content-Type", "application/json");
  if (accessToken) finalHeaders.set("Authorization", `Bearer ${accessToken}`);
  try {
    return await fetch(buildUrl(path, query), {
      ...init,
      headers: finalHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      // The refresh cookie is scoped to /api/v1/auth/, so it only travels to those endpoints.
      credentials: "include",
    });
  } catch (err) {
    throw new NetworkError(err);
  }
}

async function decode<T>(response: Response): Promise<T> {
  if (!response.ok) throw await errorFromResponse(response);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

// --- refresh -------------------------------------------------------------------------

let inFlight: Promise<Session | null> | null = null;

async function doRefresh(): Promise<Session | null> {
  const response = await send("/auth/token/refresh/", { method: "POST" });
  if (response.status === 401) {
    session.set(null);
    return null;
  }
  const data = await decode<AuthResponse>(response);
  const next = { accessToken: data.access, user: data.user };
  session.set(next);
  return next;
}

/**
 * Exchange the refresh cookie for a new access token. Concurrent callers share one
 * request, and tabs take turns through a Web Lock: the API rotates the refresh token on
 * every use, so two simultaneous refreshes would make the second look like token reuse.
 *
 * Resolves to null when the session is over (401). Throws ApiError/NetworkError when the
 * auth service is unavailable, which is not the same as being signed out.
 */
export function refreshSession(): Promise<Session | null> {
  if (!inFlight) {
    const run = () => doRefresh();
    const locked =
      typeof navigator !== "undefined" && navigator.locks
        ? navigator.locks.request("opsdesk-token-refresh", run)
        : run();
    inFlight = locked.finally(() => {
      inFlight = null;
    });
  }
  return inFlight;
}

// --- requests -------------------------------------------------------------------------

/**
 * Call the API with the current access token. On a 401 it refreshes once and retries;
 * if the refresh says the session is over, the session is cleared and the 401 is thrown.
 */
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = session.get()?.accessToken;
  let response = await send(path, options, token);

  if (response.status === 401 && token) {
    const latest = session.get()?.accessToken;
    // Another request may already have refreshed while this one was in flight.
    const renewed = latest && latest !== token ? session.get() : await refreshSession();
    if (renewed) {
      response = await send(path, options, renewed.accessToken);
    }
    if (response.status === 401) session.set(null);
  }
  return decode<T>(response);
}

// --- auth endpoints ---------------------------------------------------------------------

export const auth = {
  async login(email: string, password: string): Promise<Session> {
    const response = await send("/auth/token/", { method: "POST", body: { email, password } });
    const data = await decode<AuthResponse>(response);
    const next = { accessToken: data.access, user: data.user };
    session.set(next);
    return next;
  },

  async logout(): Promise<void> {
    try {
      await decode<void>(await send("/auth/logout/", { method: "POST" }));
    } catch (err) {
      // Signing out locally must still work when the API is unreachable.
      if (!(err instanceof ApiError) && !(err instanceof NetworkError)) throw err;
    } finally {
      session.set(null);
    }
  },
};
