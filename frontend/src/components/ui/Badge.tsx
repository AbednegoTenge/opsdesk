import type { IncidentStatus, Priority, SlaStatus } from "@/api/types";
import { PRIORITY_LABELS, SLA_LABELS, STATUS_LABELS } from "@/lib/format";

const base = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

const PRIORITY_STYLE: Record<Priority, string> = {
  critical: "bg-red-50 text-red-700 ring-red-600/20",
  high: "bg-orange-50 text-orange-700 ring-orange-600/20",
  medium: "bg-amber-50 text-amber-800 ring-amber-600/20",
  low: "bg-slate-50 text-slate-600 ring-slate-500/20",
};

const STATUS_STYLE: Record<IncidentStatus, string> = {
  open: "bg-blue-50 text-blue-700 ring-blue-600/20",
  in_progress: "bg-indigo-50 text-indigo-700 ring-indigo-600/20",
  resolved: "bg-green-50 text-green-700 ring-green-600/20",
  closed: "bg-slate-100 text-slate-600 ring-slate-500/20",
};

const SLA_STYLE: Record<SlaStatus, string> = {
  ok: "bg-green-50 text-green-700 ring-green-600/20",
  at_risk: "bg-amber-50 text-amber-800 ring-amber-600/20",
  breached: "bg-red-50 text-red-700 ring-red-600/20",
};

export const PriorityBadge = ({ value }: { value: Priority }) => (
  <span className={`${base} ${PRIORITY_STYLE[value]}`}>{PRIORITY_LABELS[value]}</span>
);

export const StatusBadge = ({ value }: { value: IncidentStatus }) => (
  <span className={`${base} ${STATUS_STYLE[value]}`}>{STATUS_LABELS[value]}</span>
);

export const SlaBadge = ({ value }: { value: SlaStatus }) => (
  <span className={`${base} ${SLA_STYLE[value]}`}>{SLA_LABELS[value]}</span>
);
