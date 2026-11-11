import type { ReactNode } from "react";

export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex items-center justify-between gap-4">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
      {actions}
    </div>
  );
}
