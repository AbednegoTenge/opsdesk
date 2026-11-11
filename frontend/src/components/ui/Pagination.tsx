export function Pagination({
  page,
  pageSize,
  count,
  onChange,
}: {
  page: number;
  pageSize: number;
  count: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (count === 0) return null;
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(count, page * pageSize);
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between py-3 text-sm text-slate-600">
      <span>
        {first}–{last} of {count}
      </span>
      <div className="flex gap-2">
        <button type="button" className="btn-secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          Previous
        </button>
        <button type="button" className="btn-secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>
          Next
        </button>
      </div>
    </nav>
  );
}
