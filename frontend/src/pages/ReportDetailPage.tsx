import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "@/api/errors";
import { keys, reports } from "@/api/resources";
import { PriorityBadge, StatusBadge } from "@/components/ui/Badge";
import { Card, ErrorState, LoadingState } from "@/components/ui/States";
import { PRIORITIES, REPORT_KIND_LABELS, STATUSES, formatDateTime, formatDuration } from "@/lib/format";
import { NotFoundPage } from "@/pages/NotFoundPage";

function Figure({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

export function ReportDetailPage() {
  const id = Number(useParams().id);
  const query = useQuery({
    queryKey: keys.report(id),
    queryFn: () => reports.get(id),
    enabled: Number.isInteger(id) && id > 0,
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 5_000 : false),
  });

  if (!Number.isInteger(id) || id <= 0) return <NotFoundPage />;
  if (query.isPending) return <LoadingState label="Loading report" />;
  if (query.isError) {
    if (query.error instanceof ApiError && query.error.status === 404) return <NotFoundPage />;
    return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  }

  const report = query.data;
  const d = report.data;

  return (
    <>
      <Link to="/reports" className="text-sm text-slate-500 hover:text-slate-900">
        ← Reports
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
        {REPORT_KIND_LABELS[report.kind]} report
      </h1>
      <p className="mb-6 text-sm text-slate-500">
        {formatDateTime(report.period_start)} to {formatDateTime(report.period_end)} (end exclusive)
      </p>

      {report.status === "pending" && <LoadingState label="The worker is generating this report" />}
      {report.status === "failed" && (
        <div role="alert" className="rounded-md bg-red-50 p-4 text-sm text-red-700">
          <p className="font-medium">This report failed to generate.</p>
          {report.error && <p className="mt-1">{report.error}</p>}
        </div>
      )}
      {report.status === "completed" && d && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Figure label="Created" value={d.created} />
            <Figure label="Resolved" value={d.resolved} />
            <Figure label="SLA breaches" value={d.sla_breaches.total} />
            <Figure label="Open now" value={d.open_now} />
            <Figure label="Mean time to acknowledge" value={formatDuration(d.mean_time_to_acknowledge_seconds)} />
            <Figure label="Mean time to resolve" value={formatDuration(d.mean_time_to_resolve_seconds)} />
            <Figure label="Response breaches" value={d.sla_breaches.response} />
            <Figure label="Resolution breaches" value={d.sla_breaches.resolution} />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Created by priority">
              <ul className="space-y-2">
                {PRIORITIES.map((p) => (
                  <li key={p} className="flex justify-between text-sm">
                    <PriorityBadge value={p} />
                    <span className="tabular-nums">{d.created_by_priority[p] ?? 0}</span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Status when generated">
              <ul className="space-y-2">
                {STATUSES.map((s) => (
                  <li key={s} className="flex justify-between text-sm">
                    <StatusBadge value={s} />
                    <span className="tabular-nums">{d.status_now[s] ?? 0}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
          <Card title="Per engineer">
            {d.per_engineer.length === 0 ? (
              <p className="text-sm text-slate-500">No assigned work in this period.</p>
            ) : (
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="py-2">Engineer</th>
                    <th className="py-2 text-right">Open now</th>
                    <th className="py-2 text-right">Resolved in period</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 tabular-nums">
                  {d.per_engineer.map((e) => (
                    <tr key={e.user_id}>
                      <td className="py-2">{e.name || e.email}</td>
                      <td className="py-2 text-right">{e.open}</td>
                      <td className="py-2 text-right">{e.resolved_in_period}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
