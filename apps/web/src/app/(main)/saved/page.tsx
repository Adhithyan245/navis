"use client";
/**
 * /saved — the user's events and bookmarks, synced to their account via
 * SavedItemsContext. "My events" (signed up) first, soonest first, then
 * other saved events, places and neighborhoods.
 */
import Link from "next/link";
import { Bookmark, CalendarDays, CircleCheck, ExternalLink, MapPin } from "lucide-react";

import { eventHref } from "@/components/runtime/EventListingCard";
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

  const soonest = (a: SavedEvent, b: SavedEvent) => (a.startsAt ?? "9999").localeCompare(b.startsAt ?? "9999");
  const today = new Date().toISOString().slice(0, 10);
  const mine = state.savedEvents.filter((e) => e.signedUp).sort(soonest);
  // Upcoming first; past events sink to the end, most recent first.
  const myEvents = [
    ...mine.filter((e) => (e.endsAt ?? e.startsAt ?? "9999").slice(0, 10) >= today),
    ...mine.filter((e) => (e.endsAt ?? e.startsAt ?? "9999").slice(0, 10) < today).reverse(),
  ];
  const otherEvents = state.savedEvents.filter((e) => !e.signedUp);

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

      {myEvents.length > 0 && (
        <Section title="My events" id="my-events">
          {myEvents.map((e) => (
            <EventRow key={e.id} event={e} />
          ))}
        </Section>
      )}

      {otherEvents.length > 0 && (
        <Section title={myEvents.length > 0 ? "Other saved events" : "Events"}>
          {otherEvents.map((e) => (
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
  id,
  children,
}: {
  title: string;
  id?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="flex scroll-mt-24 flex-col gap-3">
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

/** "Sat, Nov 2, 7:30 PM". A start without an offset is the venue's local time, shown as written. */
function when(startsAt?: string): string | null {
  if (!startsAt) return null;
  const dateOnly = startsAt.length <= 10;
  const d = new Date(dateOnly ? `${startsAt}T12:00:00` : startsAt);
  if (Number.isNaN(d.getTime())) return startsAt;
  const day = d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  return dateOnly ? day : `${day}, ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
}

function EventRow({ event }: { event: SavedEvent }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 p-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {event.source ? (
              <Link href={eventHref(event.id)} className="hover:underline">
                {event.title}
              </Link>
            ) : event.url ? (
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
              {[when(event.startsAt), event.venue].filter(Boolean).join(" · ")}
            </p>
          )}
          {event.signedUp && (
            <p className="mt-1 inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
              <CircleCheck className="size-3" /> {event.source === "ticketmaster" ? "You have tickets" : "Signed up"}
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
