import type { ReactNode } from "react";

import { Spinner } from "@/components/Spinner";
import { errorMessage } from "@/lib/errorMessage";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex justify-center py-12">
      <Spinner label={label} />
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-md bg-red-50 p-4 text-sm text-red-700">
      <p>{errorMessage(error)}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-2 font-medium underline">
          Try again
        </button>
      )}
    </div>
  );
}

export function InlineError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-sm text-red-600">
      {errorMessage(error)}
    </p>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
      {children}
    </div>
  );
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-lg bg-white shadow-sm ring-1 ring-slate-200">
      {(title || actions) && (
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          {title && <h2 className="text-sm font-semibold text-slate-900">{title}</h2>}
          {actions}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}
