import type {
  Comment,
  DashboardByAssignee,
  DashboardSummary,
  DashboardTrends,
  Incident,
  IncidentEvent,
  Notification,
  Paginated,
  UserSummary,
} from "@/api/types";

export const person = (id: number, role: UserSummary["role"] = "engineer"): UserSummary => ({
  id,
  email: `user${id}@opsdesk.test`,
  full_name: `User ${id}`,
  role,
});

export function incident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: 7,
    reference: "INC-000007",
    title: "Checkout returning 502s",
    description: "Customers can't pay.",
    priority: "high",
    status: "open",
    sla_status: "ok",
    reporter: person(2, "admin"),
    assignee: null,
    response_due_at: new Date(Date.now() + 3_600_000).toISOString(),
    resolve_due_at: new Date(Date.now() + 8 * 3_600_000).toISOString(),
    created_at: "2026-11-11T10:00:00Z",
    updated_at: "2026-11-11T10:00:00Z",
    acknowledged_at: null,
    resolved_at: null,
    closed_at: null,
    ...overrides,
  };
}

export const page = <T>(results: T[], count = results.length): Paginated<T> => ({
  count,
  next: null,
  previous: null,
  results,
});

export const comment = (overrides: Partial<Comment> = {}): Comment => ({
  id: 1,
  author: person(1),
  body: "Looking into it.",
  created_at: "2026-11-11T10:05:00Z",
  edited_at: null,
  ...overrides,
});

export const event = (overrides: Partial<IncidentEvent> = {}): IncidentEvent => ({
  id: 1,
  event_type: "created",
  actor: person(2, "admin"),
  data: {},
  created_at: "2026-11-11T10:00:00Z",
  ...overrides,
});

export const notification = (overrides: Partial<Notification> = {}): Notification => ({
  id: 1,
  kind: "incident_assigned",
  title: "INC-000007 assigned to you",
  body: "Checkout returning 502s",
  incident: 7,
  read_at: null,
  created_at: "2026-11-11T10:00:00Z",
  ...overrides,
});

export const summary: DashboardSummary = {
  total: 12,
  active: 5,
  by_status: { open: 3, in_progress: 2, resolved: 4, closed: 3 },
  active_by_priority: { critical: 1, high: 2, medium: 1, low: 1 },
  critical: { total: 2, active: 1 },
  unassigned_active: 2,
  sla: { breached_active: 1, at_risk_active: 0 },
};

export const byAssignee: DashboardByAssignee = {
  resolved_window_days: 30,
  unassigned_active: 2,
  engineers: [
    {
      id: 1,
      email: "erin@opsdesk.test",
      full_name: "Erin Engineer",
      role: "engineer",
      active: 3,
      in_progress: 2,
      critical_active: 1,
      breached_active: 0,
      resolved_recent: 9,
    },
  ],
};

export const trends: DashboardTrends = {
  days: 30,
  series: [
    { date: "2026-11-10", created: 2, resolved: 1, sla_breaches: 0 },
    { date: "2026-11-11", created: 3, resolved: 2, sla_breaches: 1 },
  ],
  totals: { created: 5, resolved: 3, sla_breaches: 1 },
  mean_time_to_resolve_seconds: 5400,
};
