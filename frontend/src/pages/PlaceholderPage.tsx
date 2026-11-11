import { PageHeader } from "@/components/PageHeader";

/** Stand-in for screens built in the next milestone. */
export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <>
      <PageHeader title={title} />
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
        {description}
      </div>
    </>
  );
}
