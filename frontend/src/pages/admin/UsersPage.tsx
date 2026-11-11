import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { keys, users } from "@/api/resources";
import type { AdminUserCreate, AdminUserUpdate, Role, User } from "@/api/types";
import { useAuth } from "@/auth/context";
import { ROLE_LABELS } from "@/auth/roles";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { EmptyState, ErrorState, InlineError, LoadingState } from "@/components/ui/States";
import { formatDate } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";

const PAGE_SIZE = 25;
const ROLES: Role[] = ["admin", "engineer", "viewer"];

const EMPTY_FORM: AdminUserCreate = { email: "", full_name: "", role: "engineer", password: "" };

function AddUserForm({ onDone }: { onDone: (created: User) => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<AdminUserCreate>(EMPTY_FORM);
  const set = (field: keyof AdminUserCreate) => (value: string) =>
    setForm((f) => ({ ...f, [field]: value }));

  const create = useMutation({
    mutationFn: () => users.create(form),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setForm(EMPTY_FORM);
      onDone(created);
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Add user"
      className="mb-6 rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200"
    >
      <h2 className="mb-3 text-sm font-semibold text-slate-900">Add a user</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="new-user-name" className="label">
            Full name
          </label>
          <input
            id="new-user-name"
            className="input"
            value={form.full_name}
            onChange={(e) => set("full_name")(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="new-user-email" className="label">
            Email
          </label>
          <input
            id="new-user-email"
            type="email"
            required
            className="input"
            value={form.email}
            onChange={(e) => set("email")(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="new-user-role" className="label">
            Role
          </label>
          <select
            id="new-user-role"
            className="input"
            value={form.role}
            onChange={(e) => set("role")(e.target.value)}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="new-user-password" className="label">
            Temporary password
          </label>
          <input
            id="new-user-password"
            type="password"
            autoComplete="new-password"
            required
            className="input"
            value={form.password}
            onChange={(e) => set("password")(e.target.value)}
          />
          <p className="mt-1 text-xs text-slate-500">
            Share it with them privately. They can change it after signing in.
          </p>
        </div>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <button type="submit" className="btn-primary" disabled={create.isPending}>
          Create user
        </button>
        <InlineError error={create.error} />
      </div>
    </form>
  );
}

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
  const [adding, setAdding] = useState(false);
  const [created, setCreated] = useState<User | null>(null);
  const debouncedSearch = useDebounced(search);
  const params = { page, page_size: PAGE_SIZE, search: debouncedSearch || undefined, role: role || undefined };

  const list = useQuery({
    queryKey: keys.users(params),
    queryFn: () => users.list(params),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageHeader
        title="Users"
        actions={
          <button
            type="button"
            className={adding ? "btn-secondary" : "btn-primary"}
            aria-expanded={adding}
            onClick={() => {
              setAdding((a) => !a);
              setCreated(null);
            }}
          >
            {adding ? "Cancel" : "Add user"}
          </button>
        }
      />
      {adding && (
        <AddUserForm
          onDone={(person) => {
            setAdding(false);
            setCreated(person);
          }}
        />
      )}
      {created && (
        <p role="status" className="mb-4 rounded-md bg-green-50 p-3 text-sm text-green-800">
          Created {created.email} as {ROLE_LABELS[created.role]}. They can sign in now.
        </p>
      )}
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
