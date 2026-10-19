"use client";
/**
 * Live departure boards for the transit stops nearest a point. Refreshes
 * every 30 seconds; shows live delays, cancellations and platforms, and
 * labels timetable-only times as "scheduled".
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, Radio, RefreshCw } from "lucide-react";

import { runtimeClient } from "@/lib/runtime/client";
import { clock, minutesUntil, type LiveBoardsResponse, type LiveDeparture } from "@/lib/transit/live";
import { cn } from "@/lib/utils";

const REFRESH_MS = 30_000;

function when(dep: LiveDeparture, now: number): string {
  const m = minutesUntil(dep.departure, now);
  if (m <= 0) return "Now";
  if (m < 60) return `${m} min`;
  return clock(dep.departure);
}

function DelayBadge({ dep }: { dep: LiveDeparture }) {
  if (dep.cancelled) return <span className="text-[11px] font-semibold text-rose-600 dark:text-rose-400">Cancelled</span>;
  if (!dep.realtime) return <span className="text-[11px] text-zinc-400">Scheduled</span>;
  const d = dep.delay_min ?? 0;
  if (d >= 2) return <span className="text-[11px] font-semibold text-amber-600 dark:text-amber-400">+{d} min</span>;
  if (d <= -2) return <span className="text-[11px] font-semibold text-sky-600 dark:text-sky-400">{Math.abs(d)} min early</span>;
  return <span className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">On time</span>;
}

export function LiveDepartures({
  lat,
  lon,
  stops = 3,
  compact = false,
}: {
  lat: number;
  lon: number;
  stops?: number;
  compact?: boolean;
}) {
  const [data, setData] = useState<LiveBoardsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const res = await runtimeClient.liveBoards(lat, lon, stops, signal);
        setData(res);
        setError(false);
      } catch {
        if (!signal?.aborted) setError(true);
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [lat, lon, stops]
  );

  useEffect(() => {
    const controller = new AbortController();
    const first = setTimeout(() => void load(controller.signal), 0);
    const refresh = setInterval(() => void load(controller.signal), REFRESH_MS);
    const tick = setInterval(() => setNow(Date.now()), 15_000);
    return () => {
      controller.abort();
      clearTimeout(first);
      clearInterval(refresh);
      clearInterval(tick);
    };
  }, [load]);

  if (loading) {
    return (
      <p className="flex items-center gap-2 text-[13px] text-zinc-500">
        <Loader2 className="size-4 animate-spin" /> Checking live departures…
      </p>
    );
  }
  if (error && !data) {
    return <p className="text-[13px] text-zinc-500">Live departures aren&apos;t loading right now. They&apos;ll retry shortly.</p>;
  }
  const boards = (data?.stops ?? []).filter((s) => s.departures.length > 0 || !compact);

  return (
    <div className="space-y-4">
      {data?.message && <p className="text-[13px] text-zinc-500 dark:text-zinc-400">{data.message}</p>}
      {boards.map((stop) => (
        <section key={stop.stop_id}>
          <div className="mb-1.5 flex items-baseline justify-between gap-2">
            <h3 className="min-w-0 truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">{stop.name}</h3>
            <span className="flex shrink-0 items-center gap-2 text-xs text-zinc-400">
              {stop.distance_m > 0 && <span>{stop.distance_m < 1000 ? `${stop.distance_m} m` : `${(stop.distance_m / 1000).toFixed(1)} km`}</span>}
              {stop.live && (
                <span className="flex items-center gap-1 font-medium text-emerald-600 dark:text-emerald-400">
                  <Radio className="size-3" /> Live
                </span>
              )}
            </span>
          </div>
          {stop.departures.length === 0 ? (
            <p className="text-[13px] text-zinc-500">No upcoming departures listed.</p>
          ) : (
            <ul className="divide-y divide-zinc-100 dark:divide-white/[0.05]">
              {stop.departures.slice(0, compact ? 4 : 6).map((d, i) => (
                <li key={`${d.line}-${d.departure}-${i}`} className={cn("flex items-center gap-2.5 py-1.5", d.cancelled && "opacity-60")}>
                  <span
                    className="min-w-9 shrink-0 rounded-md px-1.5 py-0.5 text-center text-[11px] font-bold"
                    style={{ background: d.color ?? "#e4e4e7", color: d.text_color ?? (d.color ? "#fff" : "#18181b") }}
                    title={[d.agency, d.mode].filter(Boolean).join(" · ")}
                  >
                    {d.line}
                  </span>
                  <span className={cn("min-w-0 flex-1 truncate text-[13px] text-zinc-800 dark:text-zinc-200", d.cancelled && "line-through")}>
                    {d.headsign ?? d.mode}
                    {d.platform && <span className="ml-1 text-xs text-zinc-400">· Platform {d.platform}</span>}
                  </span>
                  <span className="flex shrink-0 flex-col items-end leading-tight">
                    <span className="text-[13px] font-semibold tabular-nums text-zinc-900 dark:text-zinc-100">{when(d, now)}</span>
                    <DelayBadge dep={d} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
      <button
        type="button"
        onClick={() => void load()}
        className="flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        <RefreshCw className="size-3" /> Updates every 30 seconds
      </button>
    </div>
  );
}
