"use client";
/**
 * Track one bus / train: where it is, when it reaches the rider's stop, and
 * a stop-by-stop countdown. Data from GET /v2/transit/live/trip; the map
 * page draws the vehicle and route, this renders the panel beside it.
 */
import { Loader2, Radio, X } from "lucide-react";

import { clock, minutesUntil, type LiveTrip } from "@/lib/transit/live";
import { cn } from "@/lib/utils";

function eta(iso: string, now: number): string {
  const m = minutesUntil(iso, now);
  if (m <= 0) return "Now";
  if (m < 60) return `${m} min`;
  return clock(iso);
}

export function TripTracker({
  trip,
  loading,
  error,
  now,
  onClose,
}: {
  trip: LiveTrip | null;
  loading: boolean;
  error: boolean;
  now: number;
  onClose: () => void;
}) {
  const color = trip?.color ?? "#4f46e5";
  const yours = trip?.your_stop ?? null;
  const vehicle = trip?.vehicle ?? null;
  const where = !vehicle
    ? null
    : "position" in vehicle
    ? `At ${vehicle.at}`
    : `Between ${vehicle.from} and ${vehicle.to}`;
  const upcoming = (trip?.stops ?? []).filter((s) => !s.passed);
  const lastPassed = [...(trip?.stops ?? [])].reverse().find((s) => s.passed);

  return (
    <div>
      <div className="flex items-start gap-3">
        {trip?.line && (
          <span
            className="shrink-0 rounded-md px-2 py-0.5 text-sm font-bold"
            style={{ background: color, color: trip.text_color ?? "#fff" }}
          >
            {trip.line}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-base font-semibold text-zinc-900 dark:text-zinc-50">
            {trip?.headsign ? `To ${trip.headsign}` : trip?.line ? "Tracking" : "Finding this trip…"}
          </p>
          <p className="flex items-center gap-1.5 text-[12px] text-zinc-500">
            {trip?.realtime ? (
              <span className="flex items-center gap-1 font-medium text-emerald-600 dark:text-emerald-400">
                <Radio className="size-3" /> Live position
              </span>
            ) : trip ? (
              <span>Timetable estimate</span>
            ) : null}
            {trip?.agency && <span className="truncate">· {trip.agency}</span>}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Stop tracking"
          className="rounded-full p-1 text-zinc-400 hover:bg-zinc-100 dark:hover:bg-white/[0.06]"
        >
          <X className="size-4" />
        </button>
      </div>

      {loading && !trip && (
        <p className="mt-4 flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 className="size-4 animate-spin" /> Finding the vehicle…
        </p>
      )}
      {error && !trip && (
        <p className="mt-4 text-sm text-zinc-500">Live tracking isn&apos;t loading right now. It&apos;ll retry shortly.</p>
      )}

      {yours && (
        <div className="mt-4 rounded-2xl border border-zinc-200/80 p-3 dark:border-white/[0.08]" style={{ borderLeftColor: color, borderLeftWidth: 4 }}>
          <p className="text-[12px] text-zinc-500">Arrives at {yours.name}</p>
          <p className="text-2xl font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">
            {eta(yours.arrival, now)}
            <span className="ml-2 text-sm font-normal text-zinc-500">
              {clock(yours.arrival)}
              {yours.stops_away > 0 && ` · ${yours.stops_away} stop${yours.stops_away === 1 ? "" : "s"} away`}
            </span>
          </p>
          {yours.delay_min !== null && yours.delay_min >= 2 && (
            <p className="text-[12px] font-medium text-amber-600 dark:text-amber-400">Running {yours.delay_min} min late</p>
          )}
        </div>
      )}

      {trip?.message && <p className="mt-3 text-[13px] text-zinc-500 dark:text-zinc-400">{trip.message}</p>}
      {where && <p className="mt-3 text-[13px] text-zinc-600 dark:text-zinc-300">{where}</p>}

      {upcoming.length > 0 && (
        <ol className="relative mt-3">
          {lastPassed && (
            <li className="flex items-center gap-3 pb-2 text-[13px] text-zinc-400">
              <span className="size-2.5 shrink-0 rounded-full border-2 border-zinc-300 dark:border-zinc-600" />
              <span className="min-w-0 flex-1 truncate">{lastPassed.name}</span>
              <span className="text-xs">Departed</span>
            </li>
          )}
          {upcoming.map((s, i) => (
            <li key={`${s.name}-${s.arrival}`} className={cn("flex items-center gap-3 py-1.5 text-[13px]", s.cancelled && "opacity-60")}>
              <span
                className="size-2.5 shrink-0 rounded-full"
                style={{ background: color, ...(i === 0 ? { boxShadow: `0 0 0 4px ${color}33` } : {}) }}
              />
              <span
                className={cn(
                  "min-w-0 flex-1 truncate text-zinc-800 dark:text-zinc-200",
                  s.yours && "font-semibold text-zinc-900 dark:text-white",
                  s.cancelled && "line-through"
                )}
              >
                {s.name}
                {s.yours && <span className="ml-1.5 rounded bg-indigo-600 px-1.5 py-px text-[10px] font-semibold text-white">Your stop</span>}
              </span>
              <span className="shrink-0 text-right tabular-nums">
                <span className="font-semibold text-zinc-900 dark:text-zinc-100">{eta(s.arrival, now)}</span>
                {s.delay_min !== null && s.delay_min >= 2 && (
                  <span className="ml-1 text-[11px] text-amber-600 dark:text-amber-400">+{s.delay_min}</span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}

      <p className="mt-4 text-[11px] leading-snug text-zinc-400">
        Times and positions come from public transit data feeds and can be late, missing or wrong. Check the
        operator&apos;s signs and announcements. Updates every 20 seconds.
      </p>
    </div>
  );
}
