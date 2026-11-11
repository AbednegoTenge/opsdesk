import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { Incident } from "@/api/types";
import { comment, event, incident, page, person } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { API, backend, errorBody, makeUser, server } from "@/test/server";

function captureListQueries() {
  const seen: URLSearchParams[] = [];
  server.use(
    http.get(`${API}/incidents/`, ({ request }) => {
      seen.push(new URL(request.url).searchParams);
      return HttpResponse.json(page([incident()], 1));
    }),
  );
  return seen;
}

/** A fake incident endpoint that applies transitions/assignments and records the calls. */
function serveIncident(initial: Incident) {
  let current = initial;
  const calls: { path: string; body: unknown }[] = [];
  server.use(
    http.get(`${API}/incidents/${initial.id}/`, () => HttpResponse.json(current)),
    http.get(`${API}/incidents/${initial.id}/comments/`, () => HttpResponse.json(page([comment()]))),
    http.get(`${API}/incidents/${initial.id}/events/`, () =>
      HttpResponse.json(page([event(), event({ id: 2, event_type: "assigned", data: { to: { id: 1, email: "erin@opsdesk.test" } } })])),
    ),
    http.post(`${API}/incidents/${initial.id}/transition/`, async ({ request }) => {
      const body = (await request.json()) as { status: Incident["status"]; note: string };
      calls.push({ path: "transition", body });
      current = { ...current, status: body.status };
      return HttpResponse.json(current);
    }),
    http.post(`${API}/incidents/${initial.id}/assign/`, async ({ request }) => {
      const body = (await request.json()) as { assignee_id: number | null };
      calls.push({ path: "assign", body });
      current = { ...current, assignee: body.assignee_id ? person(body.assignee_id) : null };
      return HttpResponse.json(current);
    }),
    http.post(`${API}/incidents/${initial.id}/comments/`, async ({ request }) => {
      calls.push({ path: "comment", body: await request.json() });
      return HttpResponse.json(comment({ id: 2, body: "new" }), { status: 201 });
    }),
    http.get(`${API}/users/`, () =>
      HttpResponse.json(page([{ ...makeUser("engineer"), id: 1 }, { ...makeUser("viewer"), id: 3 }])),
    ),
  );
  return calls;
}

describe("incident list", () => {
  it("shows active incidents, newest first, by default", async () => {
    backend.refreshUser = makeUser("engineer");
    const seen = captureListQueries();
    renderApp("/incidents");

    expect(await screen.findByRole("link", { name: "Checkout returning 502s" })).toBeInTheDocument();
    expect(seen[0]?.get("status")).toBe("open,in_progress");
    expect(seen[0]?.get("ordering")).toBe("-created_at");
  });

  it("sends filters to the API and keeps them in the URL", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("engineer");
    const seen = captureListQueries();
    renderApp("/incidents?priority=critical&page=2");

    await screen.findByRole("link", { name: "Checkout returning 502s" });
    expect(seen.at(-1)?.get("priority")).toBe("critical");
    expect(seen.at(-1)?.get("page")).toBe("2");

    await user.selectOptions(screen.getByLabelText("Status"), "Any status");
    await waitFor(() => expect(seen.at(-1)?.has("status")).toBe(false));
    expect(seen.at(-1)?.get("page")).toBe("1"); // a new filter resets paging

    await user.selectOptions(screen.getByLabelText("Assignee"), "Unassigned");
    await waitFor(() => expect(seen.at(-1)?.get("assignee")).toBe("none"));
  });

  it("debounces search", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("engineer");
    const seen = captureListQueries();
    renderApp("/incidents");
    await screen.findByRole("link", { name: "Checkout returning 502s" });
    const before = seen.length;

    await user.type(screen.getByLabelText("Search"), "db-1");

    await waitFor(() => expect(seen.at(-1)?.get("search")).toBe("db-1"));
    expect(seen.length - before).toBe(1); // one request, not one per keystroke
  });

  it("offers 'New incident' to engineers but not viewers", async () => {
    backend.refreshUser = makeUser("viewer");
    captureListQueries();
    renderApp("/incidents");
    await screen.findByRole("link", { name: "Checkout returning 502s" });
    expect(screen.queryByRole("link", { name: "New incident" })).not.toBeInTheDocument();
  });
});

describe("new incident", () => {
  it("creates the incident and opens it", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("engineer");
    let sent: unknown;
    server.use(
      http.get(`${API}/users/`, () => HttpResponse.json(page([{ ...makeUser("engineer"), id: 1 }]))),
      http.post(`${API}/incidents/`, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json(incident({ id: 42, title: "DB failover" }), { status: 201 });
      }),
    );
    serveIncident(incident({ id: 42, title: "DB failover" }));
    renderApp("/incidents/new");

    await user.type(await screen.findByLabelText("Title"), "DB failover");
    await user.selectOptions(screen.getByLabelText("Priority"), "Critical");
    await user.click(screen.getByRole("button", { name: "Create incident" }));

    expect(await screen.findByRole("heading", { name: "DB failover" })).toBeInTheDocument();
    expect(sent).toEqual({ title: "DB failover", description: "", priority: "critical", assignee_id: null });
  });

  it("shows field errors from the API", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("engineer");
    server.use(
      http.get(`${API}/users/`, () => HttpResponse.json(page([]))),
      http.post(`${API}/incidents/`, () =>
        HttpResponse.json(errorBody("validation_error", "Invalid input.", { title: ["Too vague."] }), {
          status: 400,
        }),
      ),
    );
    renderApp("/incidents/new");

    await user.type(await screen.findByLabelText("Title"), "x");
    await user.click(screen.getByRole("button", { name: "Create incident" }));

    expect(await screen.findByText("Too vague.")).toBeInTheDocument();
  });

  it("is blocked for viewers", async () => {
    backend.refreshUser = makeUser("viewer");
    renderApp("/incidents/new");
    expect(await screen.findByRole("heading", { name: "You don't have access to this page" })).toBeInTheDocument();
  });
});

describe("incident detail", () => {
  it("shows the incident, its comments and its history", async () => {
    backend.refreshUser = makeUser("engineer");
    serveIncident(incident());
    renderApp("/incidents/7");

    expect(await screen.findByRole("heading", { name: "Checkout returning 502s" })).toBeInTheDocument();
    expect(screen.getByText("INC-000007")).toBeInTheDocument();
    expect(await screen.findByText("Looking into it.")).toBeInTheDocument();
    expect(await screen.findByText("assigned to erin@opsdesk.test")).toBeInTheDocument();
  });

  it("lets an engineer start work with a note", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("engineer");
    const calls = serveIncident(incident());
    renderApp("/incidents/7");

    await user.type(await screen.findByLabelText("Note (optional)"), "On it");
    await user.click(screen.getByRole("button", { name: "Start work" }));

    await waitFor(() => expect(calls).toContainEqual({ path: "transition", body: { status: "in_progress", note: "On it" } }));
    // After the move, only the transitions valid from In progress remain.
    expect(await screen.findByRole("button", { name: "Resolve" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start work" })).not.toBeInTheDocument();
  });

  it("assigns to the current user", async () => {
    const user = userEvent.setup();
    backend.refreshUser = { ...makeUser("engineer"), id: 1 };
    const calls = serveIncident(incident());
    renderApp("/incidents/7");

    await user.click(await screen.findByRole("button", { name: "Assign to me" }));

    await waitFor(() => expect(calls).toContainEqual({ path: "assign", body: { assignee_id: 1 } }));
    expect(screen.getByLabelText("Assignee")).toHaveValue("1");
    // Viewers aren't offered as assignees.
    expect(within(screen.getByLabelText("Assignee")).queryByText(/viewer/)).not.toBeInTheDocument();
  });

  it("adds a comment", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("engineer");
    const calls = serveIncident(incident());
    renderApp("/incidents/7");

    await user.type(await screen.findByLabelText("Add a comment"), "Rolled back");
    await user.click(screen.getByRole("button", { name: "Comment" }));

    await waitFor(() => expect(calls).toContainEqual({ path: "comment", body: { body: "Rolled back" } }));
  });

  it("shows the API's reason when a change is refused", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("engineer");
    serveIncident(incident());
    server.use(
      http.post(`${API}/incidents/7/transition/`, () =>
        HttpResponse.json(errorBody("invalid_transition", "Cannot move from Open to Resolved."), { status: 400 }),
      ),
    );
    renderApp("/incidents/7");

    await user.click(await screen.findByRole("button", { name: "Resolve" }));

    expect(await screen.findByText("Cannot move from Open to Resolved.")).toBeInTheDocument();
  });

  it("is read-only for viewers", async () => {
    backend.refreshUser = makeUser("viewer");
    serveIncident(incident());
    renderApp("/incidents/7");

    await screen.findByRole("heading", { name: "Checkout returning 502s" });
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Add a comment")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start work" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Assignee")).not.toBeInTheDocument();
  });

  it("only lets an Admin reopen a closed incident", async () => {
    backend.refreshUser = makeUser("engineer");
    serveIncident(incident({ status: "closed", closed_at: "2026-11-11T12:00:00Z" }));
    const { unmount } = renderApp("/incidents/7");
    await screen.findByRole("heading", { name: "Checkout returning 502s" });
    expect(screen.queryByRole("button", { name: "Reopen" })).not.toBeInTheDocument();
    unmount();

    backend.refreshUser = makeUser("admin");
    renderApp("/incidents/7");
    expect(await screen.findByRole("button", { name: "Reopen" })).toBeInTheDocument();
  });

  it("shows a not-found page for a missing incident", async () => {
    backend.refreshUser = makeUser("engineer");
    server.use(
      http.get(`${API}/incidents/999/`, () => HttpResponse.json(errorBody("not_found", "Not found."), { status: 404 })),
    );
    renderApp("/incidents/999");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
