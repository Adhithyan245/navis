"use client";
/**
 * CommuteCard — renders one commute estimate (a single mode) from the
 * commute_analysis workflow: transport mode, distance, and estimated duration.
 * Presentation only.
 */
import { Bike, Car, Footprints, Clock, Navigation, Route } from "lucide-react";
import type { ComponentType } from "react";

import { Card, CardContent } from "@/components/ui/card";
import type { Commute } from "@/lib/runtime/commute";
import { googleMapsDirectionsUrl, hasCoords } from "@/lib/runtime/maps";

const MODE_META: Record<
  string,
  { label: string; Icon: ComponentType<{ className?: string }> }
> = {
  driving: { label: "Driving", Icon: Car },
  walking: { label: "Walking", Icon: Footprints },
  cycling: { label: "Cycling", Icon: Bike },
};

function formatDuration(minutes: number): string {
  const total = Math.max(0, Math.round(minutes));
  if (total < 60) return `${total} min`;
  const h = Math.floor(total / 60);
  const m = total % 60;
  return m === 0 ? `${h} hr` : `${h} hr ${m} min`;
}

export function CommuteCard({ commute }: { commute: Commute }) {
  const meta = MODE_META[commute.mode] ?? { label: commute.mode, Icon: Route };
  const { Icon } = meta;

  return (
    <Card className="h-full">
      <CardContent className="flex h-full flex-col gap-3 p-4">
        <div className="flex items-center gap-2">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-indigo-50 dark:bg-indigo-950/50">
            <Icon className="size-4 text-indigo-500 dark:text-indigo-400" />
          </div>
          <h4 className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
            {meta.label}
          </h4>
        </div>

        <div className="flex items-center gap-4 text-sm text-zinc-700 dark:text-zinc-300">
          <span className="flex items-center gap-1">
            <Clock className="size-3.5 text-zinc-400" />
            {formatDuration(commute.durationMinutes)}
          </span>
          <span className="flex items-center gap-1">
            <Route className="size-3.5 text-zinc-400" />
            {commute.distanceKm.toFixed(1)} km
          </span>
        </div>

        <div className="mt-auto flex items-center justify-between gap-2">
          <p className="text-[10px] text-zinc-400 dark:text-zinc-500">
            via {commute.provider}
          </p>
          {hasCoords(commute.destination.lat, commute.destination.lon) && (
            <a
              href={googleMapsDirectionsUrl(
                commute.destination.lat,
                commute.destination.lon
              )}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-[10px] font-medium text-indigo-600 hover:underline dark:text-indigo-400"
            >
              <Navigation className="size-3" />
              Directions
            </a>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
