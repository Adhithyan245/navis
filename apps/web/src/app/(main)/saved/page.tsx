"use client";
/**
 * /saved — items the user bookmarked from query results. Reads entirely from
 * SavedItemsContext (localStorage); no backend. Grouped by kind, with an
 * empty state and per-item unsave via SaveButton.
 */
import { Bookmark, CalendarDays, ExternalLink, MapPin } from "lucide-react";

import { SaveButton } from "@/components/runtime/SaveButton";
import { Card, CardContent } from "@/components/ui/card";
import { useSavedItemsContext } from "@/lib/saved/context";
import type {
  SavedEvent,
  SavedNeighborhood,
  SavedPlace,
} from "@/lib/saved/schema";

export default function SavedPage() {
  const { ready, state } = useSavedItemsContext();

  if (!ready) {
    return (
      <div className="py-12 text-sm text-zinc-500 dark:text-zinc-400">
        Loading…
      </div>
    );
  }

  const total =
    state.savedPlaces.length +
    state.savedEvents.length +
    state.savedNeighborhoods.length;

  if (total === 0) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center justify-center gap-6 py-16 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-indigo-50 dark:bg-indigo-950/40">
          <Bookmark className="size-6 text-indigo-500" />
        </div>
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            Nothing saved yet
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Bookmark places and events from your query results and they&apos;ll
            show up here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-8 py-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
          Saved
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Saved to your account and synced across your devices.
        </p>
      </header>

      {state.savedPlaces.length > 0 && (
        <Section title="Places">
          {state.savedPlaces.map((p) => (
            <PlaceRow key={p.id} place={p} />
          ))}
        </Section>
      )}

      {state.savedEvents.length > 0 && (
        <Section title="Events">
          {state.savedEvents.map((e) => (
            <EventRow key={e.id} event={e} />
          ))}
        </Section>
      )}

      {state.savedNeighborhoods.length > 0 && (
        <Section title="Neighborhoods">
          {state.savedNeighborhoods.map((n) => (
            <NeighborhoodRow key={n.id} neighborhood={n} />
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        {title}
      </h2>
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  );
}

function PlaceRow({ place }: { place: SavedPlace }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 p-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {place.title}
          </p>
          {(place.area || place.city || typeof place.lat === "number") && (
            <p className="mt-0.5 flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400">
              <MapPin className="size-3" />
              {place.area || place.city || `${place.lat?.toFixed(3)}, ${place.lon?.toFixed(3)}`}
            </p>
          )}
        </div>
        <SaveButton item={place} />
      </CardContent>
    </Card>
  );
}

function EventRow({ event }: { event: SavedEvent }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 p-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {event.url ? (
              <a
                href={event.url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1 hover:underline"
              >
                {event.title}
                <ExternalLink className="size-3 opacity-50" />
              </a>
            ) : (
              event.title
            )}
          </p>
          {(event.venue || event.startsAt) && (
            <p className="mt-0.5 flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400">
              <CalendarDays className="size-3" />
              {[event.venue, event.startsAt].filter(Boolean).join(" · ")}
            </p>
          )}
        </div>
        <SaveButton item={event} />
      </CardContent>
    </Card>
  );
}

function NeighborhoodRow({
  neighborhood,
}: {
  neighborhood: SavedNeighborhood;
}) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 p-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {neighborhood.title}
          </p>
          <p className="mt-0.5 flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400">
            <MapPin className="size-3" />
            {neighborhood.area ? `${neighborhood.area}, ` : ""}
            {neighborhood.city}
          </p>
        </div>
        <SaveButton item={neighborhood} />
      </CardContent>
    </Card>
  );
}
