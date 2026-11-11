import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { keys, reports } from "@/api/resources";
import type { ReportListItem } from "@/api/types";
import { useAuth } from "@/auth/context";
import { isAdmin } from "@/auth/roles";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { Card, EmptyState, ErrorState, InlineError, LoadingState } from "@/components/ui/States";
import { REPORT_KIND_LABELS, formatDate, formatRelative } from "@/lib/format";

const PAGE_SIZE = 25;

const STATUS_STYLE: Record<ReportListItem["status"], string> = {
  pending: "text-amber-700",
  completed: "text-green-700",
  failed: "text-red-700",
};

function toDateInput(d: Date) {
  return d.toISOString().slice(0, 10);
}

function RequestReportForm() {
  const queryClient = useQueryClient();
  const today = new Date();
  const weekAgo = new Date(today.getTime() - 7 * 86_400_000);
  const [start, setStart] = useState(toDateInput(weekAgo));
  const [end, setEnd] = useState(toDateInput(today));

  const request = useMutation({
    // Whole UTC days: the end date is inclusive in the form, exclusive in the API.
    mutationFn: () => {
      const endExclusive = new Date(`${end}T00:00:00Z`);
      endExclusive.setUTCDate(endExclusive.getUTCDate() + 1);
      return reports.request(`${start}T00:00:00Z`, endExclusive.toISOString());
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.reports }),
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    request.mutate();
  }

  return (
    <Card title="Request a report">
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
          From (UTC)
          <input type="date" className="input py-1.5" value={start} max={end} onChange={(e) => setStart(e.target.value)} required />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
          To (UTC, inclusive)
          <input type="date" className="input py-1.5" value={end} min={start} onChange={(e) => setEnd(e.target.value)} required />
        </label>
        <button type="submit" className="btn-primary" disabled={request.isPending}>
          {request.isPending ? "Requesting…" : "Generate"}
        </button>
      </form>
      <div className="mt-2">
        <InlineError error={request.error} />
        {request.isSuccess && (
          <p className="text-sm text-slate-600">
            Report queued. It appears below when the worker finishes, and you'll get a notification.
          </p>
        )}
      </div>
    </Card>
  );
}

export function ReportsPage() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const list = useQuery({
    queryKey: [...keys.reports, "list", page],
    queryFn: () => reports.list(page),
    placeholderData: keepPreviousData,
    // Poll while any report on screen is still being generated.
    refetchInterval: (q) => (q.state.data?.results.some((r) => r.status === "pending") ? 5_000 : false),
  });

  return (
    <>
      <PageHeader title="Reports" />
      <div className="space-y-6">
        {isAdmin(user) && <RequestReportForm />}
        {list.isPending ? (
          <LoadingState label="Loading reports" />
        ) : list.isError ? (
          <ErrorState error={list.error} onRetry={() => list.refetch()} />
        ) : list.data.results.length === 0 ? (
          <EmptyState>No reports yet. Daily and weekly reports are generated automatically.</EmptyState>
        ) : (
          <>
            <div className="overflow-x-auto rounded-lg bg-white shadow-sm ring-1 ring-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Period</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Generated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {list.data.results.map((r) => (
                    <tr key={r.id}>
                      <td className="px-4 py-3">
                        <Link to={`/reports/${r.id}`} className="font-medium text-slate-900 hover:text-indigo-600">
                          {formatDate(r.period_start)} – {formatDate(new Date(new Date(r.period_end).getTime() - 1).toISOString())}
                        </Link>
                      </td>
                      <td className="px-4 py-3">{REPORT_KIND_LABELS[r.kind]}</td>
                      <td className={`px-4 py-3 font-medium capitalize ${STATUS_STYLE[r.status]}`}>{r.status}</td>
                      <td className="px-4 py-3 text-slate-500">{formatRelative(r.completed_at ?? r.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pageSize={PAGE_SIZE} count={list.data.count} onChange={setPage} />
          </>
        )}
      </div>
    </>
  );
}
