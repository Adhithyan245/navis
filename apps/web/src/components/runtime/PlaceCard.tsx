"use client";
/**
 * PlaceCard — renders one PlaceItem from the real backend payload.
 *
 * Field mapping matches what fusion+ranking emit for explore/work workflows:
 *   - name (required)
 *   - rating, price_level, open_now (optional, often present)
 *   - types[] (Foursquare categories or similar)
 *   - location.{lat, lng|lon} (used by future map integration)
 *   - rationale (ranking-allowlist subset)
 */
import { ExternalLink, Star, MapPin } from "lucide-react";

import { SaveButton } from "@/components/runtime/SaveButton";
import { Card, CardContent } from "@/components/ui/card";
import type { PlaceItem } from "@/lib/runtime/events";
import { googleMapsPlaceUrl } from "@/lib/runtime/maps";
import type { SavedPlace } from "@/lib/saved/schema";
import { cn } from "@/lib/utils";

interface PlaceCardProps {
  place: PlaceItem;
  className?: string;
}

export function PlaceCard({ place, className }: PlaceCardProps) {
  // Name lives at the top level for Foursquare/Ticketmaster venues; for
  // Geoapify GeoJSON Features it lives under `properties.name` (or `formatted`).
  const name =
    (typeof place.name === "string" && place.name) ||
    (typeof place.properties?.name === "string" && place.properties.name) ||
    (typeof place.properties?.formatted === "string" && place.properties.formatted) ||
    "Unnamed place";
  const rating = typeof place.rating === "number" ? place.rating : null;
  const priceLevel =
    typeof place.price_level === "number" ? place.price_level : null;
  const openNow = place.open_now === true;
  // Types: canonical `types[]`, then `properties.categories[]` (Foursquare
  // names like "Coffee Shop", or Geoapify ids like "catering.cafe.coffee").
  const rawTypes = Array.isArray(place.types)
    ? place.types
    : Array.isArray(place.properties?.categories)
    ? place.properties!.categories!
    : [];
  const types = humanizeCategories(rawTypes).slice(0, 3);

  const address =
    (typeof place.properties?.address_line2 === "string" && place.properties.address_line2) ||
    (typeof place.properties?.formatted === "string" &&
      place.properties.formatted !== name &&
      place.properties.formatted) ||
    null;
  const distanceM =
    typeof place.properties?.distance === "number" ? place.properties.distance : null;

  // Coords: canonical `location.{lat, lng|lon}` first; Geoapify exposes them
  // at `properties.{lat, lon}`.
  const lat =
    typeof place.location?.lat === "number"
      ? place.location.lat
      : typeof place.properties?.lat === "number"
      ? place.properties.lat
      : null;
  const lonRaw =
    (typeof place.location?.lng === "number" ? place.location.lng : undefined) ??
    (typeof place.location?.lon === "number" ? place.location.lon : undefined) ??
    (typeof place.properties?.lon === "number" ? place.properties.lon : undefined);
  const lon = typeof lonRaw === "number" ? lonRaw : null;

  const placeId =
    (typeof place.properties?.place_id === "string" && place.properties.place_id) ||
    (typeof place.id === "string" && place.id) ||
    name;
  const savedItem: SavedPlace = {
    kind: "place",
    id: placeId,
    title: name,
    ...(lat !== null ? { lat } : {}),
    ...(lon !== null ? { lon } : {}),
    ...(typeof place._provenance?.provider === "string"
      ? { source: place._provenance.provider }
      : {}),
    savedAt: 0,
  };

  return (
    <Card className={cn("h-full transition-all duration-300 hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-glow dark:hover:border-indigo-400/25", className)}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <h4 className="font-semibold text-sm tracking-tight text-zinc-900 dark:text-zinc-100">
            {lat !== null && lon !== null ? (
              <a
                href={googleMapsPlaceUrl(lat, lon)}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1 hover:underline"
              >
                {name}
                <ExternalLink className="size-3 opacity-50" />
              </a>
            ) : (
              name
            )}
          </h4>
          <div className="flex shrink-0 items-center gap-2">
            {rating !== null && (
              <div className="flex items-center gap-1 text-xs text-zinc-700 dark:text-zinc-300">
                <Star className="size-3 fill-amber-400 text-amber-400" />
                <span>{rating.toFixed(1)}</span>
              </div>
            )}
            <SaveButton item={savedItem} />
          </div>
        </div>

        {types.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {types.map((t) => (
              <span
                key={t}
                className="rounded-md bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-white/[0.06] dark:text-zinc-400"
              >
                {t}
              </span>
            ))}
          </div>
        )}

        <div className="mt-3 flex items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400">
          {priceLevel !== null && (
            <span title={`Price level ${priceLevel}`}>
              {"$".repeat(Math.max(1, priceLevel))}
            </span>
          )}
          {openNow && (
            <span className="text-emerald-600 dark:text-emerald-400">Open now</span>
          )}
          {(address || (lat !== null && lon !== null)) && (
            <span className="flex min-w-0 items-center gap-1">
              <MapPin className="size-3 shrink-0" />
              <span className="truncate">
                {address ? shortAddress(address) : `${lat!.toFixed(3)}, ${lon!.toFixed(3)}`}
              </span>
            </span>
          )}
          {distanceM !== null && (
            <span className="shrink-0" title={`${Math.round(distanceM)} m away`}>
              {formatDistance(distanceM)}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// Geoapify category ids that describe the building, not the place.
const GENERIC_CATEGORIES = new Set(["building", "catering", "commercial", "details", "amenity", "service"]);

/** "catering.cafe.coffee" → "Coffee"; Foursquare names pass through. Deduped. */
function humanizeCategories(raw: string[]): string[] {
  const isGeoapify = raw.some((c) => typeof c === "string" && /^[a-z_]+(\.[a-z_]+)+$/.test(c));
  const out: string[] = [];
  for (const c of raw) {
    if (typeof c !== "string" || !c || GENERIC_CATEGORIES.has(c)) continue;
    let label = c;
    if (isGeoapify) {
      const leaf = c.split(".").pop() ?? c;
      if (GENERIC_CATEGORIES.has(leaf)) continue;
      label = leaf.replace(/_/g, " ");
      label = label.charAt(0).toUpperCase() + label.slice(1);
    }
    if (!out.includes(label)) out.push(label);
  }
  // Geoapify lists ids shallow → deep; show the most specific first.
  // Foursquare already lists the primary category first.
  return isGeoapify ? out.reverse() : out;
}

/** Drop the trailing country so addresses fit on one line. */
function shortAddress(address: string): string {
  return address.replace(/,\s*United States( of America)?$/i, "");
}

function formatDistance(m: number): string {
  if (m < 1000) return `${Math.round(m / 10) * 10} m`;
  return `${(m / 1000).toFixed(1)} km`;
}
