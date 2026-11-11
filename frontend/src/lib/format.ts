import type {
  EventType,
  IncidentStatus,
  Priority,
  ReportKind,
  SlaStatus,
  UserSummary,
} from "@/api/types";

export const STATUS_LABELS: Record<IncidentStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
};

export const PRIORITY_LABELS: Record<Priority, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const SLA_LABELS: Record<SlaStatus, string> = {
  ok: "On track",
  at_risk: "At risk",
  breached: "Breached",
};

export const REPORT_KIND_LABELS: Record<ReportKind, string> = {
  daily: "Daily",
  weekly: "Weekly",
  adhoc: "On demand",
};

export const PRIORITIES: Priority[] = ["critical", "high", "medium", "low"];
export const STATUSES: IncidentStatus[] = ["open", "in_progress", "resolved", "closed"];
export const SLA_STATUSES: SlaStatus[] = ["ok", "at_risk", "breached"];

/** Mirrors TRANSITIONS in apps/incidents/services.py. The API has the final say. */
export const TRANSITIONS: Record<IncidentStatus, IncidentStatus[]> = {
  open: ["in_progress", "resolved"],
  in_progress: ["resolved"],
  resolved: ["closed", "in_progress"],
  closed: ["in_progress"],
};

export const TRANSITION_LABELS: Record<IncidentStatus, Partial<Record<IncidentStatus, string>>> = {
  open: { in_progress: "Start work", resolved: "Resolve" },
  in_progress: { resolved: "Resolve" },
  resolved: { closed: "Close", in_progress: "Reopen" },
  closed: { in_progress: "Reopen" },
};

export function personName(user: UserSummary | null | undefined, fallback = "Unassigned") {
  if (!user) return fallback;
  return user.full_name || user.email;
}

const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const dateOnly = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTime.format(new Date(iso)) : "—";
}

export function formatDate(iso: string | null | undefined): string {
  return iso ? dateOnly.format(new Date(iso)) : "—";
}

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

/** "in 3 hours", "5 minutes ago", "now". */
export function formatRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "now";
}

/** 5400 -> "1h 30m"; 200000 -> "2d 7h". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const s = Math.max(0, Math.round(seconds));
  const d = Math.floor(s / 86_400);
  const h = Math.floor((s % 86_400) / 3_600);
  const m = Math.floor((s % 3_600) / 60);
  if (d) return h ? `${d}d ${h}h` : `${d}d`;
  if (h) return m ? `${h}h ${m}m` : `${h}h`;
  if (m) return `${m}m`;
  return `${s}s`;
}

/** Minutes as the SLA screens show them: 90 -> "1h 30m". */
export const formatMinutes = (minutes: number | null | undefined) =>
  minutes === null || minutes === undefined ? "—" : formatDuration(minutes * 60);

export function describeEvent(type: EventType, data: Record<string, unknown>): string {
  const ref = (v: unknown) =>
    v && typeof v === "object" && "email" in v ? String((v as { email: string }).email) : "nobody";
  const label = (map: Record<string, string>, v: unknown) => map[String(v)] ?? String(v);
  switch (type) {
    case "created":
      return "created the incident";
    case "updated": {
      const fields = Object.keys((data.fields as object | undefined) ?? {});
      return fields.length ? `updated the ${fields.join(" and ")}` : "updated the incident";
    }
    case "priority_changed":
      return `changed priority from ${label(PRIORITY_LABELS, data.from)} to ${label(PRIORITY_LABELS, data.to)}`;
    case "assigned":
      return `assigned to ${ref(data.to)}`;
    case "unassigned":
      return `unassigned ${ref(data.from)}`;
    case "status_changed": {
      const base = `moved from ${label(STATUS_LABELS, data.from)} to ${label(STATUS_LABELS, data.to)}`;
      return data.note ? `${base}: “${String(data.note)}”` : base;
    }
    case "comment_added":
      return "commented";
    case "comment_edited":
      return "edited a comment";
    case "comment_deleted":
      return "deleted a comment";
    case "sla_breached":
      return data.target ? `breached the ${String(data.target)} SLA` : "breached its SLA";
    case "reminder_sent":
      return "reminder sent";
    default:
      return String(type).replace(/_/g, " ");
  }
}
