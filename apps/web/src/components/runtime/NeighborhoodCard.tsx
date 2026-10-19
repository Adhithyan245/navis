"use client";
/**
 * NeighborhoodCard — renders one dynamically-generated neighborhood candidate
 * (a canonical Location from the neighborhood_match workflow). Read-only
 * presentation plus a SaveButton (kind: "neighborhood").
 */
import { Car, Clock, ExternalLink, MapPin } from "lucide-react";

import { SaveButton } from "@/components/runtime/SaveButton";
import { Card, CardContent } from "@/components/ui/card";
import type { Location } from "@/lib/runtime/location";
import { googleMapsPlaceUrl, hasCoords } from "@/lib/runtime/maps";
import { locationToSaved } from "@/lib/saved/schema";

const TYPE_LABELS: Record<string, string> = {
  suburb: "Neighborhood",
  neighborhood: "Neighborhood",
  district: "District",
  city: "City / Town",
  region: "Region",
  county: "County",
};

function formatPopulation(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M people`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K people`;
  return `${n} people`;
}

function formatDuration(minutes: number): string {
  const total = Math.max(0, Math.round(minutes));
  if (total < 60) return `${total} min`;
  const h = Math.floor(total / 60);
  const m = total % 60;
  return m === 0 ? `${h} hr` : `${h} hr ${m} min`;
}

export function NeighborhoodCard({ location }: { location: Location }) {
  const savedItem = locationToSaved(location);

  const sublineParts = [
    location.district,
    location.state || location.region,
    location.country,
  ].filter((p): p is string => Boolean(p));
  const subline = sublineParts.length > 0 ? sublineParts.join(", ") : location.label;

  const description = location.short_description?.trim();
  const population =
    typeof location.population === "number" && location.population > 0
      ? formatPopulation(location.population)
      : null;
  const tags = (location.tags ?? []).filter((t) => t).slice(0, 3);
  // Commute to office (Phase 4). Present only when neighborhood_match resolved
  // an office location; lead with the driving leg.
  const commute = (location.commutes ?? [])[0] ?? null;

  return (
    <Card className="h-full">
      <CardContent className="flex h-full flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h4 className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
              {hasCoords(location.lat, location.lon) ? (
                <a
                  href={googleMapsPlaceUrl(location.lat, location.lon)}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1 hover:underline"
                >
                  {location.name}
                  <ExternalLink className="size-3 opacity-50" />
                </a>
              ) : (
                location.name
              )}
            </h4>
            <p className="mt-0.5 flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400">
              <MapPin className="size-3 shrink-0" />
              <span className="truncate">{subline}</span>
            </p>
          </div>
          <SaveButton item={savedItem} />
        </div>

        {description && (
          <p className="line-clamp-2 text-xs text-zinc-600 dark:text-zinc-300">
            {description}
          </p>
        )}

        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {tags.map((t) => (
              <span
                key={t}
                className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
              >
                {t}
              </span>
            ))}
          </div>
        )}

        {commute && (
          <div className="flex items-center gap-1.5 rounded-lg bg-zinc-50 px-2.5 py-1.5 text-xs text-zinc-600 dark:bg-zinc-800/50 dark:text-zinc-300">
            <Car className="size-3.5 shrink-0 text-indigo-500" />
            <span className="flex items-center gap-1">
              <Clock className="size-3 text-zinc-400" />
              {formatDuration(commute.durationMinutes)}
            </span>
            <span className="text-zinc-400">·</span>
            <span>{commute.distanceKm.toFixed(1)} km to office</span>
          </div>
        )}

        <div className="mt-auto flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
            {TYPE_LABELS[location.type] ?? "Place"}
          </span>
          {population && (
            <span className="text-[10px] font-medium text-zinc-500 dark:text-zinc-400">
              {population}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
