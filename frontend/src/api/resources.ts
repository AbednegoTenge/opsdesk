/** Typed calls for each API resource, plus the React Query keys that cache them. */
import { api } from "./client";
import type {
  AdminUserUpdate,
  Comment,
  DashboardByAssignee,
  DashboardSummary,
  DashboardTrends,
  Incident,
  IncidentCreate,
  IncidentEvent,
  IncidentListItem,
  IncidentStatus,
  IncidentUpdate,
  Notification,
  Paginated,
  Report,
  ReportListItem,
  SlaPolicy,
  User,
} from "./types";

export type IncidentFilters = {
  search?: string;
  status?: string;
  priority?: string;
  sla_status?: string;
  assignee?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
};

export const keys = {
  incidents: ["incidents"] as const,
  incidentList: (filters: IncidentFilters) => ["incidents", "list", filters] as const,
  incident: (id: number) => ["incidents", "detail", id] as const,
  comments: (id: number) => ["incidents", "detail", id, "comments"] as const,
  events: (id: number) => ["incidents", "detail", id, "events"] as const,
  dashboard: ["dashboard"] as const,
  notifications: ["notifications"] as const,
  unreadCount: ["notifications", "unread-count"] as const,
  reports: ["reports"] as const,
  report: (id: number) => ["reports", id] as const,
  users: (params: object) => ["users", params] as const,
  assignableUsers: ["users", "assignable"] as const,
  slaPolicies: ["sla-policies"] as const,
};

const json = (body: object) => body as Record<string, unknown>;

export const incidents = {
  list: (filters: IncidentFilters) =>
    api<Paginated<IncidentListItem>>("/incidents/", { query: filters }),
  get: (id: number) => api<Incident>(`/incidents/${id}/`),
  create: (body: IncidentCreate) =>
    api<Incident>("/incidents/", { method: "POST", body: json(body) }),
  update: (id: number, body: IncidentUpdate) =>
    api<Incident>(`/incidents/${id}/`, { method: "PATCH", body: json(body) }),
  remove: (id: number) => api<void>(`/incidents/${id}/`, { method: "DELETE" }),
  assign: (id: number, assigneeId: number | null) =>
    api<Incident>(`/incidents/${id}/assign/`, {
      method: "POST",
      body: { assignee_id: assigneeId },
    }),
  transition: (id: number, status: IncidentStatus, note = "") =>
    api<Incident>(`/incidents/${id}/transition/`, { method: "POST", body: { status, note } }),
  comments: (id: number, page = 1) =>
    api<Paginated<Comment>>(`/incidents/${id}/comments/`, { query: { page, page_size: 100 } }),
  addComment: (id: number, body: string) =>
    api<Comment>(`/incidents/${id}/comments/`, { method: "POST", body: { body } }),
  editComment: (incidentId: number, commentId: number, body: string) =>
    api<Comment>(`/incidents/${incidentId}/comments/${commentId}/`, {
      method: "PATCH",
      body: { body },
    }),
  deleteComment: (incidentId: number, commentId: number) =>
    api<void>(`/incidents/${incidentId}/comments/${commentId}/`, { method: "DELETE" }),
  events: (id: number, page = 1) =>
    api<Paginated<IncidentEvent>>(`/incidents/${id}/events/`, {
      query: { page, page_size: 100 },
    }),
};

export const dashboard = {
  summary: () => api<DashboardSummary>("/dashboard/summary/"),
  byAssignee: (days = 30) => api<DashboardByAssignee>("/dashboard/by-assignee/", { query: { days } }),
  trends: (days = 30) => api<DashboardTrends>("/dashboard/trends/", { query: { days } }),
};

export const notifications = {
  list: (page = 1, unread?: boolean) =>
    api<Paginated<Notification>>("/notifications/", {
      query: { page, unread: unread ? "true" : undefined },
    }),
  unreadCount: () => api<{ unread: number }>("/notifications/unread-count/"),
  markRead: (ids: number[]) =>
    api<{ updated: number }>("/notifications/mark-read/", { method: "POST", body: { ids, all: false } }),
  markAllRead: () =>
    api<{ updated: number }>("/notifications/mark-read/", { method: "POST", body: { all: true } }),
};

export const reports = {
  list: (page = 1) => api<Paginated<ReportListItem>>("/reports/", { query: { page } }),
  get: (id: number) => api<Report>(`/reports/${id}/`),
  request: (periodStart: string, periodEnd: string) =>
    api<Report>("/reports/", {
      method: "POST",
      body: { period_start: periodStart, period_end: periodEnd },
    }),
};

export const users = {
  list: (params: {
    page?: number;
    page_size?: number;
    search?: string;
    role?: string;
    is_active?: string;
  }) =>
    api<Paginated<User>>("/users/", { query: params }),
  update: (id: number, body: AdminUserUpdate) =>
    api<User>(`/users/${id}/`, { method: "PATCH", body: json(body) }),
};

export const slaPolicies = {
  list: () => api<SlaPolicy[]>("/sla-policies/"),
  update: (priority: string, body: Partial<Pick<SlaPolicy, "response_minutes" | "resolution_minutes" | "reminder_interval_minutes">>) =>
    api<SlaPolicy>(`/sla-policies/${priority}/`, { method: "PATCH", body: json(body) }),
};
