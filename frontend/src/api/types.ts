import type { components } from "./schema";

type Schemas = components["schemas"];

export type User = Schemas["User"];
export type Role = Schemas["RoleEnum"];
export type AuthResponse = Schemas["AuthResponse"];

export type UserSummary = Schemas["UserSummary"];
export type Priority = Schemas["PriorityEnum"];
export type IncidentStatus = Schemas["IncidentStatusEnum"];
export type SlaStatus = Schemas["SlaStatusEnum"];
export type EventType = Schemas["EventTypeEnum"];

// The schema marks reporter/assignee as always present, but the API sends null for an
// unassigned incident or a deleted reporter.
type WithPeople<T> = Omit<T, "reporter" | "assignee"> & {
  readonly reporter: UserSummary | null;
  readonly assignee: UserSummary | null;
};
export type IncidentListItem = WithPeople<Schemas["IncidentList"]>;
export type Incident = WithPeople<Schemas["IncidentDetail"]>;
export type IncidentCreate = Schemas["IncidentCreateRequest"];
export type IncidentUpdate = Schemas["PatchedIncidentUpdateRequest"];

export type Comment = Omit<Schemas["Comment"], "author"> & { readonly author: UserSummary | null };
export type IncidentEvent = Omit<Schemas["IncidentEvent"], "actor" | "data"> & {
  readonly actor: UserSummary | null;
  readonly data: Record<string, unknown>;
};

export type Notification = Schemas["Notification"];
export type ReportListItem = Schemas["ReportList"];
export type Report = Omit<Schemas["IncidentReport"], "data"> & { readonly data: ReportData | null };
export type ReportKind = Schemas["ReportKindEnum"];
export type SlaPolicy = Schemas["SLAPolicy"];
export type AdminUserUpdate = Schemas["PatchedAdminUserUpdateRequest"];

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

// Dashboard and report payloads are plain JSON objects on the API side (no serializer),
// so their shapes are declared here and kept in step with apps/reporting.
export type DashboardSummary = {
  total: number;
  active: number;
  by_status: Record<IncidentStatus, number>;
  active_by_priority: Record<Priority, number>;
  critical: { total: number; active: number };
  unassigned_active: number;
  sla: { breached_active: number; at_risk_active: number };
};

export type AssigneeLoad = {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  active: number;
  in_progress: number;
  critical_active: number;
  breached_active: number;
  resolved_recent: number;
};

export type DashboardByAssignee = {
  resolved_window_days: number;
  engineers: AssigneeLoad[];
  unassigned_active: number;
};

export type TrendPoint = { date: string; created: number; resolved: number; sla_breaches: number };

export type DashboardTrends = {
  days: number;
  series: TrendPoint[];
  totals: { created: number; resolved: number; sla_breaches: number };
  mean_time_to_resolve_seconds: number | null;
};

export type ReportData = {
  period: { start: string; end: string };
  created: number;
  resolved: number;
  created_by_priority: Record<Priority, number>;
  sla_breaches: { total: number; response: number; resolution: number };
  mean_time_to_resolve_seconds: number | null;
  mean_time_to_acknowledge_seconds: number | null;
  open_now: number;
  open_critical_now: number;
  status_now: Record<IncidentStatus, number>;
  per_engineer: {
    user_id: number;
    email: string;
    name: string;
    open: number;
    resolved_in_period: number;
  }[];
};
