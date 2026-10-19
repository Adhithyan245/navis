"use client";
/**
 * ExplorerCard — renders one dynamically-discovered place from the
 * city_explorer workflow (a canonical Location). Read-only presentation of
 * label, type, admin hierarchy, description, and tags.
 *
 * Designed so a future scoring/ranking layer can pass an optional `score`
 * without refactoring: the card stays presentation-only and the caller owns
 * ordering.
 */
import { ExternalLink, MapPin } from "lucide-react";

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
  landmark: "Place",
  street: "Street",
  postcode: "Postcode",
  address: "Address",
};

export function ExplorerCard({ location }: { location: Location }) {
  const adminParts = [
    location.city,
    location.state || location.region,
    location.country,
  ].filter((p): p is string => Boolean(p));
  const adminLine = adminParts.length > 0 ? adminParts.join(", ") : location.label;

  const description = location.short_description?.trim();
  const tags = (location.tags ?? []).filter((t) => t).slice(0, 4);
  const savedItem = locationToSaved(location);

  return (
    <Card className="h-full">
      <CardContent className="flex h-full flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <h4 className="min-w-0 text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
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
          <div className="flex shrink-0 items-center gap-1.5">
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
              {TYPE_LABELS[location.type] ?? "Place"}
            </span>
            <SaveButton item={savedItem} />
          </div>
        </div>

        <p className="flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          <MapPin className="size-3 shrink-0" />
          <span className="truncate">{adminLine}</span>
        </p>

        {description && (
          <p className="line-clamp-2 text-xs text-zinc-600 dark:text-zinc-300">
            {description}
          </p>
        )}

        {tags.length > 0 && (
          <div className="mt-auto flex flex-wrap gap-1.5">
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
      </CardContent>
    </Card>
  );
}
