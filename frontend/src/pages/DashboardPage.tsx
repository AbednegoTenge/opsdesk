import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { dashboard, keys } from "@/api/resources";
import { PageHeader } from "@/components/PageHeader";
import { TrendChart } from "@/components/TrendChart";
import { PriorityBadge } from "@/components/ui/Badge";
import { Card, ErrorState, LoadingState } from "@/components/ui/States";
import { PRIORITIES, formatDuration } from "@/lib/format";

const REFRESH_MS = 60_000;

function Stat({
  label,
  value,
  to,
  tone = "default",
}: {
  label: string;
  value: number | string;
  to?: string;
  tone?: "default" | "danger" | "warning";
}) {
  const color =
    tone === "danger" && value !== 0
      ? "text-red-600"
      : tone === "warning" && value !== 0
        ? "text-amber-600"
        : "text-slate-900";
  const body = (
    <>
      <div className="text-sm text-slate-500">{label}</div>
      <div className={`mt-1 text-3xl font-semibold tabular-nums ${color}`}>{value}</div>
    </>
  );
  const cls = "block rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200";
  return to ? (
    <Link to={to} className={`${cls} hover:ring-indigo-300`}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

function SummarySection() {
  const summary = useQuery({
    queryKey: [...keys.dashboard, "summary"],
    queryFn: dashboard.summary,
    refetchInterval: REFRESH_MS,
  });
  if (summary.isPending) return <LoadingState />;
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;
  const s = summary.data;
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="Active incidents" value={s.active} to="/incidents" />
        <Stat label="Critical, active" value={s.critical.active} tone="danger" to="/incidents?priority=critical" />
        <Stat label="SLA breached" value={s.sla.breached_active} tone="danger" to="/incidents?sla_status=breached" />
        <Stat label="SLA at risk" value={s.sla.at_risk_active} tone="warning" to="/incidents?sla_status=at_risk" />
        <Stat label="Unassigned" value={s.unassigned_active} tone="warning" to="/incidents?assignee=none" />
      </div>
      <Card title="Active by priority">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {PRIORITIES.map((p) => (
            <Link
              key={p}
              to={`/incidents?priority=${p}`}
              className="flex items-center justify-between rounded-md p-3 ring-1 ring-slate-100 hover:bg-slate-50"
            >
              <PriorityBadge value={p} />
              <span className="text-xl font-semibold tabular-nums">{s.active_by_priority[p]}</span>
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}

function TrendsSection({ days }: { days: number }) {
  const trends = useQuery({
    queryKey: [...keys.dashboard, "trends", days],
    queryFn: () => dashboard.trends(days),
    refetchInterval: REFRESH_MS,
  });
  if (trends.isPending) return <LoadingState />;
  if (trends.isError) return <ErrorState error={trends.error} onRetry={() => trends.refetch()} />;
  const t = trends.data;
  return (
    <>
      <dl className="mb-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-slate-500">Created</dt>
          <dd className="text-lg font-semibold tabular-nums">{t.totals.created}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Resolved</dt>
          <dd className="text-lg font-semibold tabular-nums">{t.totals.resolved}</dd>
        </div>
        <div>
          <dt className="text-slate-500">SLA breaches</dt>
          <dd className="text-lg font-semibold tabular-nums">{t.totals.sla_breaches}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Mean time to resolve</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatDuration(t.mean_time_to_resolve_seconds)}</dd>
        </div>
      </dl>
      <TrendChart series={t.series} />
    </>
  );
}

function WorkloadSection({ days }: { days: number }) {
  const load = useQuery({
    queryKey: [...keys.dashboard, "by-assignee", days],
    queryFn: () => dashboard.byAssignee(days),
    refetchInterval: REFRESH_MS,
  });
  if (load.isPending) return <LoadingState />;
  if (load.isError) return <ErrorState error={load.error} onRetry={() => load.refetch()} />;
  const { engineers } = load.data;
  if (engineers.length === 0) return <p className="text-sm text-slate-500">No engineers yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="py-2 pr-4">Engineer</th>
            <th className="py-2 pr-4 text-right">Active</th>
            <th className="py-2 pr-4 text-right">In progress</th>
            <th className="py-2 pr-4 text-right">Critical</th>
            <th className="py-2 pr-4 text-right">Breached</th>
            <th className="py-2 text-right">Resolved ({days}d)</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 tabular-nums">
          {engineers.map((e) => (
            <tr key={e.id}>
              <td className="py-2 pr-4 font-medium text-slate-900">{e.full_name || e.email}</td>
              <td className="py-2 pr-4 text-right">{e.active}</td>
              <td className="py-2 pr-4 text-right">{e.in_progress}</td>
              <td className={`py-2 pr-4 text-right ${e.critical_active ? "text-red-600" : ""}`}>{e.critical_active}</td>
              <td className={`py-2 pr-4 text-right ${e.breached_active ? "text-red-600" : ""}`}>{e.breached_active}</td>
              <td className="py-2 text-right">{e.resolved_recent}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DashboardPage() {
  const [days, setDays] = useState(30);
  const rangePicker = (
    <label className="flex items-center gap-2 text-sm text-slate-600">
      Period
      <select className="input w-auto py-1" value={days} onChange={(e) => setDays(Number(e.target.value))}>
        <option value={7}>Last 7 days</option>
        <option value={30}>Last 30 days</option>
        <option value={90}>Last 90 days</option>
      </select>
    </label>
  );
  return (
    <>
      <PageHeader title="Dashboard" />
      <div className="space-y-6">
        <SummarySection />
        <Card title="Trends" actions={rangePicker}>
          <TrendsSection days={days} />
        </Card>
        <Card title="Workload by engineer">
          <WorkloadSection days={days} />
        </Card>
      </div>
    </>
  );
}
