import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/errors";
import { incidents, keys } from "@/api/resources";
import type { Priority } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { InlineError } from "@/components/ui/States";
import { PRIORITIES, PRIORITY_LABELS } from "@/lib/format";
import { useAssignableUsers } from "@/lib/useAssignableUsers";

function FieldError({ error, field }: { error: unknown; field: string }) {
  if (!(error instanceof ApiError)) return null;
  const messages = error.fieldErrors[field];
  return messages ? <p className="mt-1 text-sm text-red-600">{messages.join(" ")}</p> : null;
}

export function NewIncidentPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const assignable = useAssignableUsers();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const [assigneeId, setAssigneeId] = useState("");

  const create = useMutation({
    mutationFn: () =>
      incidents.create({
        title: title.trim(),
        description: description.trim(),
        priority,
        assignee_id: assigneeId ? Number(assigneeId) : null,
      }),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: keys.incidents });
      queryClient.invalidateQueries({ queryKey: keys.dashboard });
      navigate(`/incidents/${incident.id}`, { replace: true });
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    create.mutate();
  }

  const fieldErrors = create.error instanceof ApiError ? create.error.fieldErrors : {};
  const hasFieldErrors = Object.keys(fieldErrors).length > 0;

  return (
    <>
      <PageHeader title="New incident" />
      <form
        onSubmit={handleSubmit}
        className="max-w-2xl space-y-5 rounded-lg bg-white p-6 shadow-sm ring-1 ring-slate-200"
      >
        <div>
          <label htmlFor="title" className="label">
            Title
          </label>
          <input
            id="title"
            className="input mt-1"
            required
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <FieldError error={create.error} field="title" />
        </div>
        <div>
          <label htmlFor="description" className="label">
            Description
          </label>
          <textarea
            id="description"
            className="input mt-1"
            rows={5}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <FieldError error={create.error} field="description" />
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label htmlFor="priority" className="label">
              Priority
            </label>
            <select
              id="priority"
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
            <label htmlFor="assignee" className="label">
              Assignee
            </label>
            <select
              id="assignee"
              className="input mt-1"
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value)}
            >
              <option value="">Unassigned</option>
              {assignable.data?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name || u.email}
                </option>
              ))}
            </select>
            <FieldError error={create.error} field="assignee_id" />
          </div>
        </div>
        {create.isError && !hasFieldErrors && <InlineError error={create.error} />}
        <div className="flex gap-3">
          <button type="submit" className="btn-primary" disabled={create.isPending || !title.trim()}>
            {create.isPending ? "Creating…" : "Create incident"}
          </button>
          <Link to="/incidents" className="btn-secondary">
            Cancel
          </Link>
        </div>
      </form>
    </>
  );
}
