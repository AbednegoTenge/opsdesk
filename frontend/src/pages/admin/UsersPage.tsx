import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { keys, users } from "@/api/resources";
import type { AdminUserUpdate, Role, User } from "@/api/types";
import { useAuth } from "@/auth/context";
import { ROLE_LABELS } from "@/auth/roles";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { EmptyState, ErrorState, InlineError, LoadingState } from "@/components/ui/States";
import { formatDate } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";

const PAGE_SIZE = 25;
const ROLES: Role[] = ["admin", "engineer", "viewer"];

function UserRow({ person, isSelf }: { person: User; isSelf: boolean }) {
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: (body: AdminUserUpdate) => users.update(person.id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <tr className={person.is_active ? undefined : "text-slate-400"}>
      <td className="px-4 py-3">
        <div className="font-medium text-slate-900">
          {person.full_name || "—"} {isSelf && <span className="text-xs font-normal text-slate-500">(you)</span>}
        </div>
        <div className="text-xs text-slate-500">{person.email}</div>
      </td>
      <td className="px-4 py-3">
        <select
          aria-label={`Role for ${person.email}`}
          className="input w-36 py-1"
          value={person.role}
          disabled={isSelf || update.isPending}
          onChange={(e) => update.mutate({ role: e.target.value as Role })}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-3">
        <button
          type="button"
          className="btn-secondary py-1"
          disabled={isSelf || update.isPending}
          onClick={() => update.mutate({ is_active: !person.is_active })}
        >
          {person.is_active ? "Deactivate" : "Reactivate"}
        </button>
        <InlineError error={update.error} />
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-slate-500">{formatDate(person.date_joined)}</td>
    </tr>
  );
}

export function UsersPage() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const debouncedSearch = useDebounced(search);
  const params = { page, page_size: PAGE_SIZE, search: debouncedSearch || undefined, role: role || undefined };

  const list = useQuery({
    queryKey: keys.users(params),
    queryFn: () => users.list(params),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader title="Users" />
      <p className="mb-4 text-sm text-slate-600">
        Changing someone's role or deactivating them signs them out everywhere, so their next
        sign-in picks up the change.
      </p>
      <div className="mb-4 flex flex-wrap gap-3">
        <input
          type="search"
          aria-label="Search users"
          placeholder="Search by name or email"
          className="input max-w-xs py-1.5"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
        />
        <select
          aria-label="Filter by role"
          className="input w-40 py-1.5"
          value={role}
          onChange={(e) => {
            setRole(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All roles</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </select>
      </div>
      {list.isPending ? (
        <LoadingState label="Loading users" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.data.results.length === 0 ? (
        <EmptyState>No users match.</EmptyState>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg bg-white shadow-sm ring-1 ring-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3">User</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Access</th>
                  <th className="px-4 py-3">Joined</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {list.data.results.map((u) => (
                  <UserRow key={u.id} person={u} isSelf={u.id === user?.id} />
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={PAGE_SIZE} count={list.data.count} onChange={setPage} />
        </>
      )}
    </>
  );
}
