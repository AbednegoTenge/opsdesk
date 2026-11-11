import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { API, backend, errorBody, expireAccessTokens, makeUser, server } from "@/test/server";

import { api, auth, refreshSession } from "./client";
import { ApiError, NetworkError } from "./errors";
import { session } from "./session";

describe("api client", () => {
  it("sends the access token as a bearer header", async () => {
    await auth.login("engineer@opsdesk.test", backend.password);
    const me = await api<{ email: string }>("/auth/me/");
    expect(me.email).toBe("engineer@opsdesk.test");
  });

  it("refreshes once on 401 and retries the request", async () => {
    await auth.login("engineer@opsdesk.test", backend.password);
    const before = session.get()?.accessToken;
    expireAccessTokens();

    const me = await api<{ email: string }>("/auth/me/");

    expect(me.email).toBe("engineer@opsdesk.test");
    expect(backend.refreshCalls).toBe(1);
    expect(session.get()?.accessToken).not.toBe(before);
  });

  it("shares one refresh between concurrent requests", async () => {
    await auth.login("engineer@opsdesk.test", backend.password);
    expireAccessTokens();

    await Promise.all([api("/auth/me/"), api("/auth/me/"), api("/auth/me/")]);

    // The API rotates refresh tokens, so parallel refreshes would trip reuse detection.
    expect(backend.refreshCalls).toBe(1);
  });

  it("ends the session when the refresh is rejected", async () => {
    await auth.login("engineer@opsdesk.test", backend.password);
    expireAccessTokens();
    backend.refreshUser = null; // refresh token revoked or expired

    await expect(api("/auth/me/")).rejects.toMatchObject({ status: 401 });
    expect(session.get()).toBeNull();
  });

  it("keeps the session when the auth service is down", async () => {
    await auth.login("engineer@opsdesk.test", backend.password);
    expireAccessTokens();
    backend.refreshStatus = 503;

    await expect(api("/auth/me/")).rejects.toMatchObject({ status: 503 });
    expect(session.get()).not.toBeNull();
  });

  it("decodes the error envelope", async () => {
    server.use(
      http.get(`${API}/incidents/`, () =>
        HttpResponse.json(
          errorBody("validation_error", "Invalid input.", { priority: ["Not a valid choice."] }),
          { status: 400 },
        ),
      ),
    );

    const error = await api("/incidents/").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 400, code: "validation_error", message: "Invalid input." });
    expect((error as ApiError).fieldErrors).toEqual({ priority: ["Not a valid choice."] });
  });

  it("copes with a non-JSON error page", async () => {
    server.use(
      http.get(`${API}/incidents/`, () =>
        new HttpResponse("<html>Bad gateway</html>", { status: 502, statusText: "Bad Gateway" }),
      ),
    );

    await expect(api("/incidents/")).rejects.toMatchObject({ status: 502, code: "http_502" });
  });

  it("turns a failed connection into a NetworkError", async () => {
    server.use(http.get(`${API}/incidents/`, () => HttpResponse.error()));

    await expect(api("/incidents/")).rejects.toBeInstanceOf(NetworkError);
  });

  it("builds query strings and skips empty values", async () => {
    let seen = "";
    server.use(
      http.get(`${API}/incidents/`, ({ request }) => {
        seen = new URL(request.url).search;
        return HttpResponse.json({ results: [] });
      }),
    );

    await api("/incidents/", { query: { status: "open", search: "", page: 2, assignee: null } });

    expect(seen).toBe("?status=open&page=2");
  });

  it("returns undefined for 204 responses", async () => {
    server.use(http.post(`${API}/notifications/read-all/`, () => new HttpResponse(null, { status: 204 })));
    await expect(api("/notifications/read-all/", { method: "POST" })).resolves.toBeUndefined();
  });

  it("restores a session from the refresh cookie", async () => {
    backend.refreshUser = makeUser("viewer");
    const restored = await refreshSession();
    expect(restored?.user.role).toBe("viewer");
    expect(session.get()?.accessToken).toBeTruthy();
  });

  it("clears the local session on logout even if the API is unreachable", async () => {
    await auth.login("engineer@opsdesk.test", backend.password);
    server.use(http.post(`${API}/auth/logout/`, () => HttpResponse.error()));

    await auth.logout();

    expect(session.get()).toBeNull();
  });
});
