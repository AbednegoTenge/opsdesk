import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { ReportListItem, SlaPolicy } from "@/api/types";
import { incident, notification, page } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { API, backend, errorBody, makeUser, server } from "@/test/server";

describe("dashboard", () => {
  it("shows the headline figures, trends and workload", async () => {
    backend.refreshUser = makeUser("viewer");
    renderApp("/");

    const active = await screen.findByRole("link", { name: /Active incidents/ });
    expect(active).toHaveTextContent("5");
    expect(screen.getByRole("link", { name: /SLA breached/ })).toHaveAttribute(
      "href",
      "/incidents?sla_status=breached",
    );
    expect(await screen.findByText("1h 30m")).toBeInTheDocument(); // mean time to resolve
    expect(await screen.findByRole("img", { name: /created and resolved per day/ })).toBeInTheDocument();
    expect(await screen.findByText("Erin Engineer")).toBeInTheDocument();
  });

  it("asks for a different window when the period changes", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("engineer");
    const days: string[] = [];
    server.use(
      http.get(`${API}/dashboard/trends/`, ({ request }) => {
        days.push(new URL(request.url).searchParams.get("days") ?? "");
        return HttpResponse.json({ days: 7, series: [], totals: { created: 0, resolved: 0, sla_breaches: 0 }, mean_time_to_resolve_seconds: null });
      }),
    );
    renderApp("/");

    await user.selectOptions(await screen.findByLabelText("Period"), "Last 7 days");

    await waitFor(() => expect(days).toContain("7"));
  });
});

describe("notifications", () => {
  it("shows the unread count in the header", async () => {
    backend.refreshUser = makeUser("engineer");
    server.use(http.get(`${API}/notifications/unread-count/`, () => HttpResponse.json({ unread: 3 })));
    renderApp("/");
    expect(await screen.findByRole("link", { name: "Notifications, 3 unread" })).toBeInTheDocument();
  });

  it("marks a notification read and opens its incident", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("engineer");
    let marked: unknown;
    server.use(
      http.get(`${API}/notifications/`, () => HttpResponse.json(page([notification()]))),
      http.post(`${API}/notifications/mark-read/`, async ({ request }) => {
        marked = await request.json();
        return HttpResponse.json({ updated: 1 });
      }),
      http.get(`${API}/incidents/7/`, () => HttpResponse.json(incident())),
      http.get(`${API}/incidents/7/comments/`, () => HttpResponse.json(page([]))),
      http.get(`${API}/incidents/7/events/`, () => HttpResponse.json(page([]))),
      http.get(`${API}/users/`, () => HttpResponse.json(page([]))),
    );
    renderApp("/notifications");

    await user.click(await screen.findByRole("button", { name: /assigned to you/ }));

    expect(await screen.findByRole("heading", { name: "Checkout returning 502s" })).toBeInTheDocument();
    expect(marked).toEqual({ ids: [1], all: false });
  });

  it("marks everything read", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("viewer");
    let marked: unknown;
    server.use(
      http.get(`${API}/notifications/`, () => HttpResponse.json(page([notification()]))),
      http.post(`${API}/notifications/mark-read/`, async ({ request }) => {
        marked = await request.json();
        return HttpResponse.json({ updated: 1 });
      }),
    );
    renderApp("/notifications");

    await user.click(await screen.findByRole("button", { name: "Mark all as read" }));

    await waitFor(() => expect(marked).toEqual({ all: true }));
  });
});

const report = (overrides: Partial<ReportListItem> = {}): ReportListItem => ({
  id: 1,
  kind: "daily",
  period_start: "2026-11-10T00:00:00Z",
  period_end: "2026-11-11T00:00:00Z",
  status: "completed",
  error: "",
  requested_by: null,
  created_at: "2026-11-11T07:00:00Z",
  completed_at: "2026-11-11T07:00:05Z",
  ...overrides,
});

describe("reports", () => {
  it("lists reports for engineers without the request form", async () => {
    backend.refreshUser = makeUser("engineer");
    server.use(http.get(`${API}/reports/`, () => HttpResponse.json(page([report()]))));
    renderApp("/reports");

    expect(await screen.findByText("Daily")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate" })).not.toBeInTheDocument();
  });

  it("lets an Admin request a report over whole UTC days", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("admin");
    let sent: { period_start: string; period_end: string } | undefined;
    server.use(
      http.get(`${API}/reports/`, () => HttpResponse.json(page([]))),
      http.post(`${API}/reports/`, async ({ request }) => {
        sent = (await request.json()) as typeof sent;
        return HttpResponse.json(report({ kind: "adhoc", status: "pending" }), { status: 202 });
      }),
    );
    renderApp("/reports");

    const from = await screen.findByLabelText("From (UTC)");
    const to = screen.getByLabelText("To (UTC, inclusive)");
    await user.clear(to);
    await user.type(to, "2026-11-07");
    await user.clear(from);
    await user.type(from, "2026-11-01");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(await screen.findByText(/Report queued/)).toBeInTheDocument();
    expect(sent).toEqual({
      period_start: "2026-11-01T00:00:00Z",
      period_end: "2026-11-08T00:00:00.000Z", // the inclusive end date becomes an exclusive bound
    });
  });

  it("shows why a report failed", async () => {
    backend.refreshUser = makeUser("engineer");
    server.use(
      http.get(`${API}/reports/5/`, () =>
        HttpResponse.json({ ...report({ id: 5, status: "failed", error: "Database timeout" }), data: null }),
      ),
    );
    renderApp("/reports/5");
    expect(await screen.findByText("Database timeout")).toBeInTheDocument();
  });
});

describe("users (admin)", () => {
  it("changes a role and can't change their own", async () => {
    const user = userEvent.setup();
    const admin = { ...makeUser("admin"), id: 10 };
    backend.refreshUser = admin;
    let patched: unknown;
    server.use(
      http.get(`${API}/users/`, () =>
        HttpResponse.json(page([admin, { ...makeUser("viewer"), id: 11 }])),
      ),
      http.patch(`${API}/users/11/`, async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json({ ...makeUser("engineer"), id: 11 });
      }),
    );
    renderApp("/users");

    expect(await screen.findByLabelText("Role for admin@opsdesk.test")).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Role for viewer@opsdesk.test"), "Engineer");

    await waitFor(() => expect(patched).toEqual({ role: "engineer" }));
  });

  it("shows the API's refusal", async () => {
    const user = userEvent.setup();
    backend.refreshUser = { ...makeUser("admin"), id: 10 };
    server.use(
      http.get(`${API}/users/`, () => HttpResponse.json(page([{ ...makeUser("viewer"), id: 11 }]))),
      http.patch(`${API}/users/11/`, () =>
        HttpResponse.json(errorBody("validation_error", "Invalid input.", { is_active: ["Nope."] }), { status: 400 }),
      ),
    );
    renderApp("/users");

    await user.click(await screen.findByRole("button", { name: "Deactivate" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("is_active: Nope.");
  });
});

describe("adding users (admin)", () => {
  it("creates an engineer from the Users screen", async () => {
    const user = userEvent.setup();
    backend.refreshUser = { ...makeUser("admin"), id: 10 };
    let posted: unknown;
    server.use(
      http.get(`${API}/users/`, () => HttpResponse.json(page([backend.refreshUser!]))),
      http.post(`${API}/users/`, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(
          { ...makeUser("engineer"), id: 12, email: "new.eng@opsdesk.test" },
          { status: 201 },
        );
      }),
    );
    renderApp("/users");

    await user.click(await screen.findByRole("button", { name: "Add user" }));
    const form = screen.getByRole("form", { name: "Add user" });
    expect(within(form).getByLabelText("Role")).toHaveValue("engineer");
    await user.type(within(form).getByLabelText("Full name"), "New Eng");
    await user.type(within(form).getByLabelText("Email"), "new.eng@opsdesk.test");
    await user.type(within(form).getByLabelText("Temporary password"), "Sturdy-pass-2026");
    await user.click(within(form).getByRole("button", { name: "Create user" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Created new.eng@opsdesk.test as Engineer",
    );
    expect(posted).toEqual({
      email: "new.eng@opsdesk.test",
      full_name: "New Eng",
      role: "engineer",
      password: "Sturdy-pass-2026",
    });
    expect(screen.queryByRole("form", { name: "Add user" })).not.toBeInTheDocument();
  });

  it("keeps the form open and shows the API's refusal", async () => {
    const user = userEvent.setup();
    backend.refreshUser = { ...makeUser("admin"), id: 10 };
    server.use(
      http.get(`${API}/users/`, () => HttpResponse.json(page([backend.refreshUser!]))),
      http.post(`${API}/users/`, () =>
        HttpResponse.json(
          errorBody("validation_error", "Invalid input.", {
            email: ["A user with this email already exists."],
          }),
          { status: 400 },
        ),
      ),
    );
    renderApp("/users");

    await user.click(await screen.findByRole("button", { name: "Add user" }));
    const form = screen.getByRole("form", { name: "Add user" });
    await user.type(within(form).getByLabelText("Email"), "taken@opsdesk.test");
    await user.type(within(form).getByLabelText("Temporary password"), "Sturdy-pass-2026");
    await user.click(within(form).getByRole("button", { name: "Create user" }));

    expect(await within(form).findByRole("alert")).toHaveTextContent(
      "A user with this email already exists.",
    );
    expect(within(form).getByLabelText("Email")).toHaveValue("taken@opsdesk.test");
  });
});

describe("SLA policies (admin)", () => {
  const policy: SlaPolicy = {
    priority: "medium",
    response_minutes: 240,
    resolution_minutes: 1440,
    reminder_interval_minutes: null,
    updated_at: "2026-11-11T10:00:00Z",
  };

  it("edits targets and turns reminders on", async () => {
    const user = userEvent.setup();
    backend.refreshUser = makeUser("admin");
    let patched: unknown;
    server.use(
      http.get(`${API}/sla-policies/`, () => HttpResponse.json([policy])),
      http.patch(`${API}/sla-policies/medium/`, async ({ request }) => {
        patched = await request.json();
        return HttpResponse.json({ ...policy, ...(patched as object) });
      }),
    );
    renderApp("/settings/sla");

    const row = (await screen.findByText("Medium")).closest("tr")!;
    expect(within(row).getByText("4h")).toBeInTheDocument();
    expect(within(row).getByText("Off")).toBeInTheDocument();

    await user.click(within(row).getByRole("button", { name: "Edit" }));
    const response = screen.getByLabelText("Response target (minutes)");
    await user.clear(response);
    await user.type(response, "120");
    await user.type(screen.getByLabelText("Reminder interval (minutes)"), "60");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(patched).toEqual({ response_minutes: 120, resolution_minutes: 1440, reminder_interval_minutes: 60 }),
    );
  });
});
