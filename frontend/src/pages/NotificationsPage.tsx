import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { keys, notifications } from "@/api/resources";
import type { Notification } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { EmptyState, ErrorState, InlineError, LoadingState } from "@/components/ui/States";
import { formatDateTime, formatRelative } from "@/lib/format";

const PAGE_SIZE = 25;

export function NotificationsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);

  const list = useQuery({
    queryKey: [...keys.notifications, "list", page, unreadOnly],
    queryFn: () => notifications.list(page, unreadOnly),
    placeholderData: keepPreviousData,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.notifications });
  const markRead = useMutation({ mutationFn: (ids: number[]) => notifications.markRead(ids), onSuccess: refresh });
  const markAll = useMutation({ mutationFn: notifications.markAllRead, onSuccess: refresh });

  function open(n: Notification) {
    if (!n.read_at) markRead.mutate([n.id]);
    if (n.incident) navigate(`/incidents/${n.incident}`);
    else if (n.kind === "report") navigate("/reports");
  }

  return (
    <>
      <PageHeader
        title="Notifications"
        actions={
          <button type="button" className="btn-secondary" disabled={markAll.isPending} onClick={() => markAll.mutate()}>
            Mark all as read
          </button>
        }
      />
      <label className="mb-4 flex items-center gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={unreadOnly}
          onChange={(e) => {
            setUnreadOnly(e.target.checked);
            setPage(1);
          }}
        />
        Unread only
      </label>
      <InlineError error={markAll.error ?? markRead.error} />
      {list.isPending ? (
        <LoadingState label="Loading notifications" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.data.results.length === 0 ? (
        <EmptyState>{unreadOnly ? "You're all caught up." : "No notifications yet."}</EmptyState>
      ) : (
        <>
          <ul className="divide-y divide-slate-100 overflow-hidden rounded-lg bg-white shadow-sm ring-1 ring-slate-200">
            {list.data.results.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => open(n)}
                  className={`flex w-full gap-3 px-4 py-3 text-left hover:bg-slate-50 ${n.read_at ? "" : "bg-indigo-50/40"}`}
                >
                  <span
                    aria-label={n.read_at ? undefined : "Unread"}
                    className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.read_at ? "bg-transparent" : "bg-indigo-600"}`}
                  />
                  <span className="flex-1">
                    <span className={`block text-sm ${n.read_at ? "text-slate-700" : "font-semibold text-slate-900"}`}>
                      {n.title}
                    </span>
                    {n.body && <span className="mt-0.5 line-clamp-2 block text-sm text-slate-500">{n.body}</span>}
                  </span>
                  <span className="whitespace-nowrap text-xs text-slate-500" title={formatDateTime(n.created_at)}>
                    {formatRelative(n.created_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <Pagination page={page} pageSize={PAGE_SIZE} count={list.data.count} onChange={setPage} />
        </>
      )}
    </>
  );
}
