import type { ReactNode } from "react";

/** A centred message, either filling the viewport or inside the app layout (embedded). */
export function FullPageMessage({
  title,
  children,
  embedded = false,
}: {
  title: string;
  children?: ReactNode;
  embedded?: boolean;
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center px-4 text-center ${
        embedded ? "py-24" : "min-h-screen"
      }`}
    >
      <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
      <div className="mt-2 text-sm text-slate-600">{children}</div>
    </div>
  );
}
