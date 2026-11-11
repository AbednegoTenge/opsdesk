import { useQuery } from "@tanstack/react-query";

import { incidents, keys } from "@/api/resources";
import { Card, ErrorState, LoadingState } from "@/components/ui/States";
import { describeEvent, formatDateTime, formatRelative, personName } from "@/lib/format";

export function ActivityTimeline({ incidentId }: { incidentId: number }) {
  const events = useQuery({
    queryKey: keys.events(incidentId),
    queryFn: () => incidents.events(incidentId),
  });

  return (
    <Card title="Activity">
      {events.isPending ? (
        <LoadingState label="Loading activity" />
      ) : events.isError ? (
        <ErrorState error={events.error} onRetry={() => events.refetch()} />
      ) : (
        <ol className="space-y-3">
          {events.data.results.map((event) => (
            <li key={event.id} className="flex gap-3 text-sm">
              <span
                aria-hidden
                className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                  event.event_type === "sla_breached" ? "bg-red-500" : "bg-slate-300"
                }`}
              />
              <div>
                <span className="font-medium text-slate-900">{personName(event.actor, "OpsDesk")}</span>{" "}
                <span className="text-slate-700">{describeEvent(event.event_type, event.data)}</span>
                <div className="text-xs text-slate-500" title={formatDateTime(event.created_at)}>
                  {formatRelative(event.created_at)}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
