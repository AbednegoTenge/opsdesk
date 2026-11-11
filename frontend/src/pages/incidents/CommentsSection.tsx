import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { incidents, keys } from "@/api/resources";
import type { Comment } from "@/api/types";
import { useAuth } from "@/auth/context";
import { canEditIncidents, isAdmin } from "@/auth/roles";
import { Card, ErrorState, InlineError, LoadingState } from "@/components/ui/States";
import { formatRelative, personName } from "@/lib/format";

function CommentItem({ incidentId, comment }: { incidentId: number; comment: Comment }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState(comment.body);
  const canChange = !!user && (isAdmin(user) || comment.author?.id === user.id);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: keys.comments(incidentId) });
    queryClient.invalidateQueries({ queryKey: keys.events(incidentId) });
  };
  const save = useMutation({
    mutationFn: () => incidents.editComment(incidentId, comment.id, body.trim()),
    onSuccess: () => {
      setEditing(false);
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: () => incidents.deleteComment(incidentId, comment.id),
    onSuccess: refresh,
  });

  return (
    <li className="py-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-slate-900">
          {personName(comment.author, "Deleted user")}
        </span>
        <span className="text-xs text-slate-500">
          {formatRelative(comment.created_at)}
          {comment.edited_at && " (edited)"}
        </span>
      </div>
      {editing ? (
        <div className="mt-2 space-y-2">
          <textarea
            aria-label="Edit comment"
            className="input"
            rows={3}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <InlineError error={save.error} />
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-primary"
              disabled={!body.trim() || save.isPending}
              onClick={() => save.mutate()}
            >
              Save
            </button>
            <button type="button" className="btn-secondary" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{comment.body}</p>
      )}
      {canChange && !editing && (
        <div className="mt-1 flex gap-3 text-xs">
          <button type="button" className="text-slate-500 hover:text-slate-900" onClick={() => setEditing(true)}>
            Edit
          </button>
          <button
            type="button"
            className="text-slate-500 hover:text-red-600"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            Delete
          </button>
        </div>
      )}
      <InlineError error={remove.error} />
    </li>
  );
}

export function CommentsSection({ incidentId }: { incidentId: number }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const comments = useQuery({
    queryKey: keys.comments(incidentId),
    queryFn: () => incidents.comments(incidentId),
  });
  const add = useMutation({
    mutationFn: () => incidents.addComment(incidentId, body.trim()),
    onSuccess: () => {
      setBody("");
      queryClient.invalidateQueries({ queryKey: keys.comments(incidentId) });
      queryClient.invalidateQueries({ queryKey: keys.events(incidentId) });
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    add.mutate();
  }

  return (
    <Card title={`Comments${comments.data ? ` (${comments.data.count})` : ""}`}>
      {comments.isPending ? (
        <LoadingState label="Loading comments" />
      ) : comments.isError ? (
        <ErrorState error={comments.error} onRetry={() => comments.refetch()} />
      ) : comments.data.results.length === 0 ? (
        <p className="text-sm text-slate-500">No comments yet.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {comments.data.results.map((c) => (
            <CommentItem key={c.id} incidentId={incidentId} comment={c} />
          ))}
        </ul>
      )}
      {canEditIncidents(user) && (
        <form onSubmit={handleSubmit} className="mt-4 space-y-2 border-t border-slate-100 pt-4">
          <label htmlFor="new-comment" className="label">
            Add a comment
          </label>
          <textarea
            id="new-comment"
            className="input"
            rows={3}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <InlineError error={add.error} />
          <button type="submit" className="btn-primary" disabled={!body.trim() || add.isPending}>
            {add.isPending ? "Posting…" : "Comment"}
          </button>
        </form>
      )}
    </Card>
  );
}
