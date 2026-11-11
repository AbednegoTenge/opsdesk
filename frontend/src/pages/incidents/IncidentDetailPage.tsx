import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "@/api/errors";
import { incidents, keys } from "@/api/resources";
import type { Incident, IncidentStatus, Priority } from "@/api/types";
import { useAuth } from "@/auth/context";
import { canEditIncidents, isAdmin } from "@/auth/roles";
import { PriorityBadge, SlaBadge, StatusBadge } from "@/components/ui/Badge";
import { Card, ErrorState, InlineError, LoadingState } from "@/components/ui/States";
import { NotFoundPage } from "@/pages/NotFoundPage";
import {
  PRIORITIES,
  PRIORITY_LABELS,
  TRANSITIONS,
  TRANSITION_LABELS,
  formatDateTime,
  formatRelative,
  personName,
} from "@/lib/format";
import { useAssignableUsers } from "@/lib/useAssignableUsers";

import { ActivityTimeline } from "./ActivityTimeline";
import { CommentsSection } from "./CommentsSection";

/** Shared cache updates after any change to an incident. */
function useIncidentChanged(id: number) {
  const queryClient = useQueryClient();
  return (incident?: Incident) => {
    if (incident) queryClient.setQueryData(keys.incident(id), incident);
    // A transition note is also saved as a comment, so refresh both.
    queryClient.invalidateQueries({ queryKey: keys.events(id) });
    queryClient.invalidateQueries({ queryKey: keys.comments(id) });
    queryClient.invalidateQueries({ queryKey: ["incidents", "list"] });
    queryClient.invalidateQueries({ queryKey: keys.dashboard });
  };
}

function DueTime({ label, due, met }: { label: string; due: string | null; met: boolean }) {
  if (!due) return null;
  const overdue = !met && new Date(due).getTime() < Date.now();
  return (
    <Row label={label}>
      <span className={overdue ? "font-medium text-red-600" : undefined} title={formatDateTime(due)}>
        {met ? "Met" : formatRelative(due)}
      </span>
    </Row>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right text-slate-900">{children}</dd>
    </div>
  );
}

function EditForm({ incident, onDone }: { incident: Incident; onDone: () => void }) {
  const changed = useIncidentChanged(incident.id);
  const [title, setTitle] = useState(incident.title);
  const [description, setDescription] = useState(incident.description);
  const [priority, setPriority] = useState<Priority>(incident.priority);

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, string> = {};
      if (title.trim() !== incident.title) body.title = title.trim();
      if (description !== incident.description) body.description = description;
      if (priority !== incident.priority) body.priority = priority;
      return incidents.update(incident.id, body);
    },
    onSuccess: (updated) => {
      changed(updated);
      onDone();
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="edit-title" className="label">
          Title
        </label>
        <input id="edit-title" className="input mt-1" value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div>
        <label htmlFor="edit-priority" className="label">
          Priority
        </label>
        <select
          id="edit-priority"
          className="input mt-1"
          value={priority}
          onChange={(e) => setPriority(e.target.value as Priority)}
        >
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {PRIORITY_LABELS[p]}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="edit-description" className="label">
          Description
        </label>
        <textarea
          id="edit-description"
          className="input mt-1"
          rows={6}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <InlineError error={save.error} />
      <div className="flex gap-2">
        <button type="submit" className="btn-primary" disabled={!title.trim() || save.isPending}>
          {save.isPending ? "Saving…" : "Save changes"}
        </button>
        <button type="button" className="btn-secondary" onClick={onDone}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function StatusActions({ incident }: { incident: Incident }) {
  const { user } = useAuth();
  const changed = useIncidentChanged(incident.id);
  const [note, setNote] = useState("");
  const move = useMutation({
    mutationFn: (to: IncidentStatus) => incidents.transition(incident.id, to, note.trim()),
    onSuccess: (updated) => {
      setNote("");
      changed(updated);
    },
  });

  // Only Admins can reopen a closed incident.
  const targets =
    incident.status === "closed" && !isAdmin(user) ? [] : TRANSITIONS[incident.status];
  if (targets.length === 0) return null;

  return (
    <Card title="Status">
      <label htmlFor="transition-note" className="label">
        Note (optional)
      </label>
      <input
        id="transition-note"
        className="input mt-1"
        placeholder="e.g. Root cause and fix"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="mt-3 flex flex-wrap gap-2">
        {targets.map((to) => (
          <button
            key={to}
            type="button"
            className={to === "resolved" ? "btn-primary" : "btn-secondary"}
            disabled={move.isPending}
            onClick={() => move.mutate(to)}
          >
            {TRANSITION_LABELS[incident.status][to]}
          </button>
        ))}
      </div>
      <div className="mt-2">
        <InlineError error={move.error} />
      </div>
    </Card>
  );
}

function AssigneeControl({ incident }: { incident: Incident }) {
  const { user } = useAuth();
  const changed = useIncidentChanged(incident.id);
  const assignable = useAssignableUsers();
  const assign = useMutation({
    mutationFn: (id: number | null) => incidents.assign(incident.id, id),
    onSuccess: (updated) => changed(updated),
  });

  if (!canEditIncidents(user) || incident.status === "closed") {
    return <>{personName(incident.assignee)}</>;
  }
  return (
    <div className="flex flex-col items-end gap-1">
      <select
        aria-label="Assignee"
        className="input w-48 py-1"
        value={incident.assignee?.id ?? ""}
        disabled={assign.isPending}
        onChange={(e) => assign.mutate(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">Unassigned</option>
        {/* Keep the current assignee selectable even if they're no longer assignable. */}
        {incident.assignee && !assignable.data?.some((u) => u.id === incident.assignee?.id) && (
          <option value={incident.assignee.id}>{personName(incident.assignee)}</option>
        )}
        {assignable.data?.map((u) => (
          <option key={u.id} value={u.id}>
            {u.full_name || u.email}
          </option>
        ))}
      </select>
      {user && incident.assignee?.id !== user.id && (
        <button
          type="button"
          className="text-xs font-medium text-indigo-600 hover:text-indigo-500"
          disabled={assign.isPending}
          onClick={() => assign.mutate(user.id)}
        >
          Assign to me
        </button>
      )}
      <InlineError error={assign.error} />
    </div>
  );
}

function DeleteButton({ incident }: { incident: Incident }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const remove = useMutation({
    mutationFn: () => incidents.remove(incident.id),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: keys.incident(incident.id) });
      queryClient.invalidateQueries({ queryKey: keys.incidents });
      queryClient.invalidateQueries({ queryKey: keys.dashboard });
      navigate("/incidents", { replace: true });
    },
  });

  if (!confirming) {
    return (
      <button type="button" className="text-sm font-medium text-red-600 hover:text-red-500" onClick={() => setConfirming(true)}>
        Delete incident
      </button>
    );
  }
  return (
    <div className="rounded-md bg-red-50 p-3 text-sm text-red-800">
      <p>Delete this incident, its comments and its history? This can't be undone.</p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          className="btn-primary bg-red-600 hover:bg-red-500"
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
        >
          Yes, delete
        </button>
        <button type="button" className="btn-secondary" onClick={() => setConfirming(false)}>
          Keep it
        </button>
      </div>
      <InlineError error={remove.error} />
    </div>
  );
}

export function IncidentDetailPage() {
  const { id: rawId } = useParams();
  const id = Number(rawId);
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const query = useQuery({
    queryKey: keys.incident(id),
    queryFn: () => incidents.get(id),
    enabled: Number.isInteger(id) && id > 0,
  });

  if (!Number.isInteger(id) || id <= 0) return <NotFoundPage />;
  if (query.isPending) return <LoadingState label="Loading incident" />;
  if (query.isError) {
    if (query.error instanceof ApiError && query.error.status === 404) return <NotFoundPage />;
    return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  }

  const incident = query.data;
  const editable = canEditIncidents(user) && incident.status !== "closed";

  return (
    <>
      <div className="mb-6">
        <Link to="/incidents" className="text-sm text-slate-500 hover:text-slate-900">
          ← Incidents
        </Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-slate-500">{incident.reference}</p>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{incident.title}</h1>
            <div className="mt-2 flex flex-wrap gap-2">
              <PriorityBadge value={incident.priority} />
              <StatusBadge value={incident.status} />
              <SlaBadge value={incident.sla_status} />
            </div>
          </div>
          {editable && !editing && (
            <button type="button" className="btn-secondary" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Description">
            {editing ? (
              <EditForm incident={incident} onDone={() => setEditing(false)} />
            ) : incident.description ? (
              <p className="whitespace-pre-wrap text-sm text-slate-700">{incident.description}</p>
            ) : (
              <p className="text-sm text-slate-500">No description.</p>
            )}
          </Card>
          <CommentsSection incidentId={incident.id} />
        </div>

        <div className="space-y-6">
          <Card title="Details">
            <dl className="divide-y divide-slate-100">
              <Row label="Assignee">
                <AssigneeControl incident={incident} />
              </Row>
              <Row label="Reporter">{personName(incident.reporter, "Deleted user")}</Row>
              <Row label="Created">{formatDateTime(incident.created_at)}</Row>
              <DueTime label="Response due" due={incident.response_due_at} met={!!incident.acknowledged_at} />
              <DueTime label="Resolution due" due={incident.resolve_due_at} met={!!incident.resolved_at} />
              {incident.acknowledged_at && <Row label="Acknowledged">{formatDateTime(incident.acknowledged_at)}</Row>}
              {incident.resolved_at && <Row label="Resolved">{formatDateTime(incident.resolved_at)}</Row>}
              {incident.closed_at && <Row label="Closed">{formatDateTime(incident.closed_at)}</Row>}
            </dl>
          </Card>
          {canEditIncidents(user) && <StatusActions incident={incident} />}
          <ActivityTimeline incidentId={incident.id} />
          {isAdmin(user) && <DeleteButton incident={incident} />}
        </div>
      </div>
    </>
  );
}
