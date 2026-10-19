"use client";
/**
 * LocationCollectionCard — renders one saved canonical location from the
 * unified collection. Read-only presentation plus a SaveButton (which, since
 * the item is already saved, acts as an unsave toggle).
 */
import { ExternalLink, MapPin } from "lucide-react";

import { SaveButton } from "@/components/runtime/SaveButton";
import { Card, CardContent } from "@/components/ui/card";
import { googleMapsPlaceUrl } from "@/lib/runtime/maps";
import type { SavedLocation } from "@/lib/saved/schema";

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

export function LocationCollectionCard({ item }: { item: SavedLocation }) {
  const adminParts = [item.city, item.state, item.country].filter(
    (p): p is string => Boolean(p)
  );
  const adminLine = adminParts.join(", ");
  const tags = (item.tags ?? []).filter((t) => t).slice(0, 4);
  const lat = item.lat;
  const lon = item.lon;
  const mapsUrl =
    typeof lat === "number" && typeof lon === "number"
      ? googleMapsPlaceUrl(lat, lon)
      : null;

  return (
    <Card className="h-full">
      <CardContent className="flex h-full flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <h4 className="min-w-0 text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
            {mapsUrl ? (
              <a
                href={mapsUrl}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1 hover:underline"
              >
                {item.label}
                <ExternalLink className="size-3 opacity-50" />
              </a>
            ) : (
              item.label
            )}
          </h4>
          <div className="flex shrink-0 items-center gap-1.5">
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
              {TYPE_LABELS[item.type] ?? "Place"}
            </span>
            <SaveButton item={item} />
          </div>
        </div>

        {adminLine && (
          <p className="flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400">
            <MapPin className="size-3 shrink-0" />
            <span className="truncate">{adminLine}</span>
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
