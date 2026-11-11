import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { incidents, keys, type IncidentFilters } from "@/api/resources";
import { useAuth } from "@/auth/context";
import { canEditIncidents } from "@/auth/roles";
import { PageHeader } from "@/components/PageHeader";
import { PriorityBadge, SlaBadge, StatusBadge } from "@/components/ui/Badge";
import { Pagination } from "@/components/ui/Pagination";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import {
  PRIORITIES,
  PRIORITY_LABELS,
  SLA_LABELS,
  SLA_STATUSES,
  STATUS_LABELS,
  STATUSES,
  formatRelative,
  personName,
} from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";

const PAGE_SIZE = 25;
const ACTIVE = "open,in_progress";

const ORDERINGS: Record<string, string> = {
  "-created_at": "Newest first",
  created_at: "Oldest first",
  "-priority": "Most urgent first",
  resolve_due_at: "Due soonest",
  "-updated_at": "Recently updated",
};

/** Filters live in the URL, so a filtered list can be bookmarked and shared. */
function useFilters() {
  const [params, setParams] = useSearchParams();
  const filters: IncidentFilters = {
    search: params.get("search") ?? undefined,
    status: params.get("status") ?? ACTIVE,
    priority: params.get("priority") ?? undefined,
    sla_status: params.get("sla_status") ?? undefined,
    assignee: params.get("assignee") ?? undefined,
    ordering: params.get("ordering") ?? "-created_at",
    page: Number(params.get("page")) || 1,
    page_size: PAGE_SIZE,
  };

  function update(changes: Partial<Record<keyof IncidentFilters, string | number | undefined>>) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(changes)) {
          if (value === undefined || value === "") next.delete(key);
          else next.set(key, String(value));
        }
        if (!("page" in changes)) next.delete("page"); // new filter -> back to page 1
        return next;
      },
      { replace: true },
    );
  }
  return { filters, update };
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
      {label}
      <select className="input py-1.5" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([v, text]) => (
          <option key={v} value={v}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

export function IncidentsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { filters, update } = useFilters();
  const [search, setSearch] = useState(filters.search ?? "");
  const debouncedSearch = useDebounced(search);

  useEffect(() => {
    if ((filters.search ?? "") !== debouncedSearch) update({ search: debouncedSearch });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  const apiFilters = { ...filters, status: filters.status === "all" ? undefined : filters.status };
  const query = useQuery({
    queryKey: keys.incidentList(apiFilters),
    queryFn: () => incidents.list(apiFilters),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Incidents"
        actions={
          canEditIncidents(user) && (
            <Link to="/incidents/new" className="btn-primary">
              New incident
            </Link>
          )
        }
      />

      <div className="mb-4 grid gap-3 rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:grid-cols-2 lg:grid-cols-6">
        <label className="flex flex-col gap-1 text-xs font-medium text-slate-600 lg:col-span-2">
          Search
          <input
            type="search"
            className="input py-1.5"
            placeholder="Title, description or reference"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <Select
          label="Status"
          value={filters.status ?? ""}
          onChange={(v) => update({ status: v || "all" })}
          options={[
            [ACTIVE, "Active"],
            ...STATUSES.map((s): [string, string] => [s, STATUS_LABELS[s]]),
            ["all", "Any status"],
          ]}
        />
        <Select
          label="Priority"
          value={filters.priority ?? ""}
          onChange={(v) => update({ priority: v })}
          options={[["", "Any priority"], ...PRIORITIES.map((p): [string, string] => [p, PRIORITY_LABELS[p]])]}
        />
        <Select
          label="SLA"
          value={filters.sla_status ?? ""}
          onChange={(v) => update({ sla_status: v })}
          options={[["", "Any SLA"], ...SLA_STATUSES.map((s): [string, string] => [s, SLA_LABELS[s]])]}
        />
        <Select
          label="Assignee"
          value={filters.assignee ?? ""}
          onChange={(v) => update({ assignee: v })}
          options={[
            ["", "Anyone"],
            ["me", "Assigned to me"],
            ["none", "Unassigned"],
          ]}
        />
        <Select
          label="Sort"
          value={filters.ordering ?? "-created_at"}
          onChange={(v) => update({ ordering: v })}
          options={Object.entries(ORDERINGS)}
        />
      </div>

      {query.isPending ? (
        <LoadingState label="Loading incidents" />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : query.data.results.length === 0 ? (
        <EmptyState>No incidents match these filters.</EmptyState>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg bg-white shadow-sm ring-1 ring-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3">Incident</th>
                  <th className="px-4 py-3">Priority</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">SLA</th>
                  <th className="px-4 py-3">Assignee</th>
                  <th className="px-4 py-3">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {query.data.results.map((incident) => (
                  <tr
                    key={incident.id}
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={() => navigate(`/incidents/${incident.id}`)}
                  >
                    <td className="max-w-md px-4 py-3">
                      <Link
                        to={`/incidents/${incident.id}`}
                        className="font-medium text-slate-900 hover:text-indigo-600"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {incident.title}
                      </Link>
                      <div className="text-xs text-slate-500">{incident.reference}</div>
                    </td>
                    <td className="px-4 py-3">
                      <PriorityBadge value={incident.priority} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge value={incident.status} />
                    </td>
                    <td className="px-4 py-3">
                      <SlaBadge value={incident.sla_status} />
                    </td>
                    <td className="px-4 py-3 text-slate-700">{personName(incident.assignee)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                      {formatRelative(incident.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={filters.page ?? 1}
            pageSize={PAGE_SIZE}
            count={query.data.count}
            onChange={(page) => update({ page })}
          />
        </>
      )}
    </>
  );
}
