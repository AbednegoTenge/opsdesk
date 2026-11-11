import type { TrendPoint } from "@/api/types";
import { formatDate } from "@/lib/format";

const SERIES = [
  { key: "created", label: "Created", className: "fill-indigo-500", swatch: "bg-indigo-500" },
  { key: "resolved", label: "Resolved", className: "fill-emerald-500", swatch: "bg-emerald-500" },
] as const;

/** Daily created vs resolved, as paired bars. Breaches are listed below the chart. */
export function TrendChart({ series }: { series: TrendPoint[] }) {
  const width = 640;
  const height = 160;
  const max = Math.max(1, ...series.flatMap((p) => [p.created, p.resolved]));
  const slot = width / Math.max(1, series.length);
  const bar = Math.max(1, Math.min(10, slot / 2 - 1));
  const summary = series
    .map((p) => `${p.date}: ${p.created} created, ${p.resolved} resolved`)
    .join("; ");

  return (
    <figure>
      <svg
        viewBox={`0 0 ${width} ${height + 18}`}
        className="h-48 w-full"
        role="img"
        aria-label={`Incidents created and resolved per day. ${summary}`}
        preserveAspectRatio="none"
      >
        <line x1={0} x2={width} y1={height} y2={height} className="stroke-slate-200" />
        {series.map((point, i) => {
          const x = i * slot + slot / 2;
          return (
            <g key={point.date}>
              <title>
                {formatDate(point.date)}: {point.created} created, {point.resolved} resolved
                {point.sla_breaches ? `, ${point.sla_breaches} SLA breaches` : ""}
              </title>
              {SERIES.map((s, j) => {
                const value = point[s.key];
                const h = (value / max) * (height - 4);
                return (
                  <rect
                    key={s.key}
                    x={x + (j === 0 ? -bar - 0.5 : 0.5)}
                    y={height - h}
                    width={bar}
                    height={h}
                    rx={1}
                    className={s.className}
                  />
                );
              })}
              {point.sla_breaches > 0 && (
                <circle cx={x} cy={height + 9} r={3} className="fill-red-500" />
              )}
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-4 text-xs text-slate-600">
        {SERIES.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className={`h-2.5 w-2.5 rounded-sm ${s.swatch}`} />
            {s.label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-red-500" />
          Day with an SLA breach
        </span>
        <span className="ml-auto text-slate-400">
          {series[0] && formatDate(series[0].date)} – {series.at(-1) && formatDate(series.at(-1)!.date)}
        </span>
      </figcaption>
    </figure>
  );
}
