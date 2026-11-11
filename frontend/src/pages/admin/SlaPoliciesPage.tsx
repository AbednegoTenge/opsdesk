import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { keys, slaPolicies } from "@/api/resources";
import type { SlaPolicy } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { PriorityBadge } from "@/components/ui/Badge";
import { ErrorState, InlineError, LoadingState } from "@/components/ui/States";
import { formatMinutes, formatRelative } from "@/lib/format";

function PolicyRow({ policy }: { policy: SlaPolicy }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [response, setResponse] = useState(String(policy.response_minutes));
  const [resolution, setResolution] = useState(String(policy.resolution_minutes));
  const [reminder, setReminder] = useState(policy.reminder_interval_minutes?.toString() ?? "");

  const save = useMutation({
    mutationFn: () =>
      slaPolicies.update(policy.priority, {
        response_minutes: Number(response),
        resolution_minutes: Number(resolution),
        reminder_interval_minutes: reminder === "" ? null : Number(reminder),
      }),
    onSuccess: () => {
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: keys.slaPolicies });
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  if (!editing) {
    return (
      <tr>
        <td className="px-4 py-3">
          <PriorityBadge value={policy.priority} />
        </td>
        <td className="px-4 py-3 tabular-nums">{formatMinutes(policy.response_minutes)}</td>
        <td className="px-4 py-3 tabular-nums">{formatMinutes(policy.resolution_minutes)}</td>
        <td className="px-4 py-3 tabular-nums">
          {policy.reminder_interval_minutes ? `Every ${formatMinutes(policy.reminder_interval_minutes)}` : "Off"}
        </td>
        <td className="px-4 py-3 text-slate-500">{formatRelative(policy.updated_at)}</td>
        <td className="px-4 py-3 text-right">
          <button type="button" className="btn-secondary py-1" onClick={() => setEditing(true)}>
            Edit
          </button>
        </td>
      </tr>
    );
  }

  const formId = `sla-${policy.priority}`;
  const input = (label: string, value: string, set: (v: string) => void, required = true) => (
    <input
      aria-label={`${label} (minutes)`}
      form={formId}
      type="number"
      min={1}
      required={required}
      placeholder={required ? undefined : "Off"}
      className="input w-28 py-1"
      value={value}
      onChange={(e) => set(e.target.value)}
    />
  );

  return (
    <tr className="bg-indigo-50/40">
      <td className="px-4 py-3">
        <PriorityBadge value={policy.priority} />
      </td>
      <td className="px-4 py-3">{input("Response target", response, setResponse)}</td>
      <td className="px-4 py-3">{input("Resolution target", resolution, setResolution)}</td>
      <td className="px-4 py-3">{input("Reminder interval", reminder, setReminder, false)}</td>
      <td className="px-4 py-3" colSpan={2}>
        <form id={formId} onSubmit={handleSubmit} className="flex justify-end gap-2">
          <button type="submit" className="btn-primary py-1" disabled={save.isPending}>
            Save
          </button>
          <button type="button" className="btn-secondary py-1" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </form>
        <InlineError error={save.error} />
      </td>
    </tr>
  );
}

export function SlaPoliciesPage() {
  const list = useQuery({ queryKey: keys.slaPolicies, queryFn: slaPolicies.list });

  return (
    <>
      <PageHeader title="SLA policies" />
      <p className="mb-4 text-sm text-slate-600">
        Targets in minutes from when an incident is created. Changes apply to incidents created, or
        given a new priority, after you save. Other incidents keep the due times they already have.
      </p>
      {list.isPending ? (
        <LoadingState label="Loading SLA policies" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : (
        <div className="overflow-x-auto rounded-lg bg-white shadow-sm ring-1 ring-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3">Respond within</th>
                <th className="px-4 py-3">Resolve within</th>
                <th className="px-4 py-3">Reminders</th>
                <th className="px-4 py-3">Updated</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.map((p) => (
                <PolicyRow key={p.priority} policy={p} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
