"use client";
/**
 * EventCard — renders one EventItem from the real backend payload.
 *
 * Event shape varies by provider (Ticketmaster vs Eventbrite), so we
 * read each logical field (title, categories, venue, url, date) from
 * multiple possible locations and fall back gracefully when fields are
 * absent. No normalization layer — just defensive field access.
 */
import { CalendarDays, ExternalLink, MapPin } from "lucide-react";

import { SaveButton } from "@/components/runtime/SaveButton";
import { Card, CardContent } from "@/components/ui/card";
import type { EventItem } from "@/lib/runtime/events";
import { googleMapsPlaceUrl } from "@/lib/runtime/maps";
import type { SavedEvent } from "@/lib/saved/schema";
import { cn } from "@/lib/utils";

function toNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

interface EventCardProps {
  event: EventItem;
  className?: string;
}

export function EventCard({ event, className }: EventCardProps) {
  // Title: canonical `title`, then Ticketmaster `name`.
  const title =
    (typeof event.title === "string" && event.title) ||
    (typeof event.name === "string" && event.name) ||
    "Untitled event";

  // Categories: canonical `categories[]`, then Ticketmaster `classifications[].segment/genre`.
  let categories: string[] = [];
  if (Array.isArray(event.categories)) {
    categories = event.categories.filter((c): c is string => typeof c === "string");
  } else if (Array.isArray(event.classifications)) {
    const seen = new Set<string>();
    for (const c of event.classifications) {
      for (const n of [c?.segment?.name, c?.genre?.name, c?.subGenre?.name]) {
        if (typeof n === "string" && n && !seen.has(n)) {
          seen.add(n);
          categories.push(n);
        }
      }
    }
  }
  categories = categories.slice(0, 3);

  // Venue + date are TM-shape extras; render when present, omit otherwise.
  const venue = event._embedded?.venues?.[0];
  const venueName = typeof venue?.name === "string" ? venue.name : null;
  const venueCity = typeof venue?.city?.name === "string" ? venue.city.name : null;
  const venueLat = toNum(venue?.location?.latitude);
  const venueLon = toNum(venue?.location?.longitude);
  const venueMapsUrl =
    venueLat !== null && venueLon !== null
      ? googleMapsPlaceUrl(venueLat, venueLon)
      : null;
  const date = event.dates?.start;
  const dateLabel = date?.localDate
    ? `${date.localDate}${date.localTime ? ` · ${date.localTime}` : ""}`
    : null;
  const url = typeof event.url === "string" ? event.url : null;

  const eventId =
    (typeof event.id === "string" && event.id) || url || title;
  const savedItem: SavedEvent = {
    kind: "event",
    id: eventId,
    title,
    ...(venueName ? { venue: venueName } : {}),
    ...(venueCity ? { city: venueCity } : {}),
    ...(url ? { url } : {}),
    ...(date?.dateTime ? { startsAt: date.dateTime } : {}),
    ...(typeof event._provenance?.provider === "string"
      ? { source: event._provenance.provider }
      : {}),
    savedAt: 0,
  };

  return (
    <Card className={cn("h-full transition-all duration-300 hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-glow dark:hover:border-indigo-400/25", className)}>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-100 to-fuchsia-100 dark:from-indigo-500/20 dark:to-fuchsia-500/10">
            <CalendarDays className="size-4 text-indigo-500 dark:text-indigo-400" />
          </div>
          <div className="min-w-0 flex-1">
            <h4 className="font-semibold text-sm tracking-tight text-zinc-900 dark:text-zinc-100 truncate">
              {url ? (
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1 hover:underline"
                >
                  {title}
                  <ExternalLink className="size-3 opacity-50" />
                </a>
              ) : (
                title
              )}
            </h4>
            {(venueName || dateLabel) && (
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-zinc-500 dark:text-zinc-400">
                {venueName &&
                  (venueMapsUrl ? (
                    <a
                      href={venueMapsUrl}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-1 hover:underline"
                    >
                      <MapPin className="size-3" />
                      {venueName}
                      {venueCity ? `, ${venueCity}` : ""}
                    </a>
                  ) : (
                    <span className="inline-flex items-center gap-1">
                      <MapPin className="size-3" />
                      {venueName}
                      {venueCity ? `, ${venueCity}` : ""}
                    </span>
                  ))}
                {dateLabel && <span>{dateLabel}</span>}
              </div>
            )}
            {categories.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {categories.map((c) => (
                  <span
                    key={c}
                    className="rounded-full bg-indigo-50 dark:bg-indigo-950/50 px-2 py-0.5 text-[10px] font-medium text-indigo-600 dark:text-indigo-400"
                  >
                    {c}
                  </span>
                ))}
              </div>
            )}
          </div>
          <SaveButton item={savedItem} />
        </div>
      </CardContent>
    </Card>
  );
}
