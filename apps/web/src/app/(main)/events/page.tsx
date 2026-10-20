"use client";
/**
 * /events — what's on near a place: concerts, sports, theatre, comedy,
 * family, film, community, tech conferences and public holidays.
 *
 * Defaults to the profile's city; the user can search any other place or
 * use their current location. Filters: category, date range, keyword.
 * Each card opens /events/[id] with the full details.
 */
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { CalendarDays, CircleCheck, Info, LocateFixed, Loader2, Search, X } from "lucide-react";

import { EventListingCard } from "@/components/runtime/EventListingCard";
import { LocationSearch } from "@/components/runtime/LocationSearch";
import { Button } from "@/components/ui/button";
import { runtimeClient } from "@/lib/runtime/client";
import {
  DATE_RANGES,
  dateRange,
  dayHeading,
  toISODay,
  type DateRangeKey,
} from "@/lib/runtime/event-format";
import {
  EVENT_CATEGORIES,
  type EventCategory,
  type EventsSearchResponse,
} from "@/lib/runtime/listings";
import type { Location } from "@/lib/runtime/location";
import { useProfileContext } from "@/lib/profile/context";
import { sourceName } from "@/lib/runtime/event-format";
import { useSavedItemsContext } from "@/lib/saved/context";
import { cn } from "@/lib/utils";

type LoadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; data: EventsSearchResponse }
  | { status: "error"; message: string };

// useSearchParams needs a Suspense boundary (Next 16 docs: use-search-params).
export default function EventsPage() {
  return (
    <Suspense fallback={<div className="py-12 text-sm text-zinc-500">Loading…</div>}>
      <EventsPageInner />
    </Suspense>
  );
}

function initialCategory(raw: string | null): EventCategory | null {
  return EVENT_CATEGORIES.some((c) => c.value === raw) ? (raw as EventCategory) : null;
}

function EventsPageInner() {
  const { ready, profile } = useProfileContext();
  const searchParams = useSearchParams();
  const [place, setPlace] = useState<Location | null>(null);
  const [seeded, setSeeded] = useState(false);
  const [category, setCategory] = useState<EventCategory | null>(() =>
    initialCategory(searchParams.get("category"))
  );
  const [range, setRange] = useState<DateRangeKey>("month");
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const [state, setState] = useState<LoadState>({ status: "idle" });
  const [locating, setLocating] = useState(false);
  const [locateError, setLocateError] = useState<string | null>(null);

  // Seed the place from the profile once it's loaded (set-during-render).
  if (!seeded && ready) {
    setSeeded(true);
    if (profile?.cityLocation) setPlace(profile.cityLocation);
  }

  useEffect(() => {
    if (!place) return;
    const controller = new AbortController();
    const { from, to } = dateRange(range);
    // Defer the state write so it isn't a synchronous set in the effect body.
    const handle = setTimeout(() => setState({ status: "loading" }), 0);
    runtimeClient
      .eventsSearch(
        {
          lat: place.lat,
          lon: place.lon,
          city: place.city || place.name,
          countryCode: place.country_code,
          country: place.country,
          region: place.region,
          category,
          dateFrom: from,
          dateTo: to,
          keyword: keyword || undefined,
        },
        controller.signal
      )
      .then((data) => {
        clearTimeout(handle);
        setState({ status: "done", data });
      })
      .catch(() => {
        clearTimeout(handle);
        if (controller.signal.aborted) return;
        setState({ status: "error", message: "We couldn't load events right now. Please try again." });
      });
    return () => {
      clearTimeout(handle);
      controller.abort();
    };
  }, [place, category, range, keyword]);

  const useMyLocation = () => {
    if (!("geolocation" in navigator)) {
      setLocateError("Your browser can't share location.");
      return;
    }
    setLocating(true);
    setLocateError(null);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const loc = await runtimeClient
          .geocodeReverse(pos.coords.latitude, pos.coords.longitude)
          .catch(() => null);
        setLocating(false);
        if (loc) setPlace(loc);
        else setLocateError("Couldn't work out where you are. Try searching instead.");
      },
      () => {
        setLocating(false);
        setLocateError("Location permission was denied. Search for a place instead.");
      },
      { timeout: 10_000, maximumAge: 300_000 }
    );
  };

  // Local events grouped by day ("now" = started before today and still on);
  // online / out-of-town conferences get their own section so they don't
  // lead a city's listings.
  const { groups, remote } = useMemo(() => {
    if (state.status !== "done") return { groups: [], remote: [] };
    const today = toISODay(new Date());
    const byDay = new Map<string, EventsSearchResponse["events"]>();
    const remoteList: EventsSearchResponse["events"] = [];
    for (const e of state.data.events) {
      // Online, or a tech event elsewhere in the country (e.g. a hackathon in
      // another city): grouped below the local listings.
      if (e.locality === "online" || e.locality === "elsewhere" || (e.locality === "country" && e.category === "tech")) {
        remoteList.push(e);
        continue;
      }
      const key = !e.start_date ? "tba" : e.start_date < today ? "now" : e.start_date;
      const list = byDay.get(key) ?? [];
      list.push(e);
      byDay.set(key, list);
    }
    const order = (k: string) => (k === "now" ? "0" : k === "tba" ? "9" : `1${k}`);
    const entries = [...byDay.entries()].sort((a, b) => order(a[0]).localeCompare(order(b[0])));
    return { groups: entries, remote: remoteList };
  }, [state]);

  const placeName = place ? place.city || place.name : null;

  return (
    <div className="mx-auto flex w-full min-w-0 max-w-6xl flex-col gap-6">
      <header className="flex flex-col gap-2">
        <p className="inline-flex w-fit items-center gap-2 rounded-full border border-indigo-200/70 bg-indigo-50/70 px-3 py-1 text-xs font-medium text-indigo-700 dark:border-indigo-400/20 dark:bg-indigo-500/10 dark:text-indigo-300">
          <CalendarDays className="size-3.5" aria-hidden />
          Events
        </p>
        <h1 className="text-3xl font-semibold tracking-[-0.02em] text-zinc-900 sm:text-4xl dark:text-zinc-50">
          What&apos;s on{placeName ? <> in <span className="text-gradient">{placeName}</span></> : null}
        </h1>
        <p className="text-[15px] text-zinc-500 dark:text-zinc-400">
          Concerts, sports, theatre, comedy, tech conferences, festivals and holidays, with times,
          venues and tickets.
        </p>
      </header>

      {/* Place picker */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <LocationSearch
            value={place?.label ?? ""}
            onSelect={setPlace}
            near={profile?.cityLocation}
            placeholder="Search any city, town, island or address"
          />
        </div>
        <Button variant="outline" size="sm" onClick={useMyLocation} disabled={locating}>
          {locating ? <Loader2 className="animate-spin" /> : <LocateFixed />}
          Use my location
        </Button>
      </div>
      {locateError && <p className="text-xs text-rose-600 dark:text-rose-400">{locateError}</p>}

      {/* Filters */}
      <div className="flex min-w-0 flex-col gap-3">
        <div className="no-scrollbar -mx-1 flex min-w-0 gap-2 overflow-x-auto px-1 pb-1" role="group" aria-label="Category">
          <Chip active={category === null} onClick={() => setCategory(null)}>
            All
          </Chip>
          {EVENT_CATEGORIES.map((c) => {
            const count = state.status === "done" && category === null ? state.data.counts[c.value] : undefined;
            return (
              <Chip key={c.value} active={category === c.value} onClick={() => setCategory(c.value)}>
                {c.label}
                {count ? <span className="ml-1 text-[11px] opacity-60">{count}</span> : null}
              </Chip>
            );
          })}
        </div>
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="no-scrollbar -mx-1 flex min-w-0 gap-1.5 overflow-x-auto px-1" role="group" aria-label="Dates">
            {DATE_RANGES.map((r) => (
              <button
                key={r.key}
                type="button"
                onClick={() => setRange(r.key)}
                aria-pressed={range === r.key}
                className={cn(
                  "shrink-0 rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors",
                  range === r.key
                    ? "bg-indigo-600 text-white"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-white/[0.06]"
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
          <form
            className="relative shrink-0 sm:w-64"
            onSubmit={(e) => {
              e.preventDefault();
              setKeyword(keywordInput.trim());
            }}
          >
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-400" aria-hidden />
            <input
              value={keywordInput}
              onChange={(e) => setKeywordInput(e.target.value)}
              placeholder="Artist, team, topic…"
              aria-label="Search events"
              maxLength={80}
              className="w-full rounded-lg border border-zinc-200 bg-white py-2 pl-9 pr-8 text-sm outline-none placeholder:text-zinc-400 focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
            {keyword && (
              <button
                type="button"
                aria-label="Clear search"
                onClick={() => {
                  setKeywordInput("");
                  setKeyword("");
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-zinc-400 hover:text-zinc-700"
              >
                <X className="size-3.5" />
              </button>
            )}
          </form>
        </div>
      </div>

      <MyEventsLink />

      {/* Results */}
      {!place && ready && (
        <EmptyState
          title="Pick a place to see what's on"
          body="Search any city, town or island above, or use your current location."
        />
      )}

      {state.status === "loading" && <LoadingGrid />}

      {state.status === "error" && <EmptyState title="Something went wrong" body={state.message} />}

      {state.status === "done" && (
        <>
          {state.data.coverage_note && (
            <div className="flex items-start gap-2 rounded-xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-[13px] text-amber-900 dark:border-amber-400/20 dark:bg-amber-500/10 dark:text-amber-200">
              <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>{state.data.coverage_note}</span>
            </div>
          )}
          {groups.length === 0 && remote.length === 0 ? (
            <EmptyState
              title="No events found"
              body="Try a wider date range, another category, or a nearby city."
            />
          ) : (
            <div className="flex flex-col gap-8">
              {groups.map(([day, events]) => (
                <EventGroup
                  key={day}
                  title={day === "now" ? "Happening now" : dayHeading(day === "tba" ? null : day)}
                  events={events}
                />
              ))}
              {remote.length > 0 && (
                <EventGroup
                  title="Online & further afield"
                  hint="Join from anywhere, or plan a trip."
                  events={remote}
                />
              )}
            </div>
          )}
          {state.data.sources.length > 0 && (
            <p className="text-center text-[11px] text-zinc-400">
              Listings from {state.data.sources.map(sourceName).join(", ")}. Check the organiser&apos;s page before you go.
            </p>
          )}
          {category === "tech" && (
            <p className="mx-auto max-w-2xl text-center text-[11px] text-zinc-400">
              Tech listings come from Luma, Devpost, MLH, dev.events and confs.tech. LinkedIn, Meetup and
              Eventbrite don&apos;t offer public event search, so their events show here only when organisers
              also post them on one of these platforms.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function EventGroup({
  title,
  hint,
  events,
}: {
  title: string;
  hint?: string;
  events: EventsSearchResponse["events"];
}) {
  return (
    <section aria-label={title}>
      <h2 className="mb-3 text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
        {title}
        <span className="ml-2 text-xs font-normal text-zinc-400">{collapseSessions(events).length}</span>
        {hint && <span className="ml-2 text-xs font-normal text-zinc-500">{hint}</span>}
      </h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {collapseSessions(events).map(({ event, more }) => (
          <EventListingCard key={event.id} event={event} moreTimes={more} />
        ))}
      </div>
    </section>
  );
}

/** Same title at the same venue on the same day (hourly tours, matinee +
 *  evening shows) → one card showing the first session and a count. */
function collapseSessions(events: EventsSearchResponse["events"]) {
  const seen = new Map<string, { event: EventsSearchResponse["events"][number]; more: number }>();
  const out: Array<{ event: EventsSearchResponse["events"][number]; more: number }> = [];
  for (const e of events) {
    const key = `${e.title.toLowerCase()}|${e.venue.name ?? ""}|${e.start_date ?? ""}`;
    const hit = seen.get(key);
    if (hit) {
      hit.more += 1;
      continue;
    }
    const entry = { event: e, more: 0 };
    seen.set(key, entry);
    out.push(entry);
  }
  return out;
}



function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "shrink-0 rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-all",
        active
          ? "border-zinc-900 bg-zinc-900 text-white dark:border-white dark:bg-white dark:text-zinc-900"
          : "border-zinc-200/80 bg-white/70 text-zinc-600 hover:border-indigo-300 hover:text-indigo-700 dark:border-white/[0.08] dark:bg-zinc-900/60 dark:text-zinc-300"
      )}
    >
      {children}
    </button>
  );
}

/** "You're signed up for N upcoming events" → the list in Saved. */
function MyEventsLink() {
  const { state, ready } = useSavedItemsContext();
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = state.savedEvents.filter(
    (e) => e.signedUp && (e.endsAt ?? e.startsAt ?? "9999").slice(0, 10) >= today
  );
  if (!ready || upcoming.length === 0) return null;
  return (
    <Link
      href="/saved#my-events"
      className="flex items-center gap-2 rounded-xl border border-emerald-200/80 bg-emerald-50/80 px-4 py-3 text-[13px] font-medium text-emerald-900 hover:bg-emerald-50 dark:border-emerald-400/20 dark:bg-emerald-500/10 dark:text-emerald-200"
    >
      <CircleCheck className="size-4 shrink-0" aria-hidden />
      You&apos;re signed up for {upcoming.length} upcoming event{upcoming.length === 1 ? "" : "s"}
      <span className="ml-auto text-emerald-700 dark:text-emerald-300">See them →</span>
    </Link>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-zinc-300/80 px-6 py-14 text-center dark:border-white/10">
      <p className="font-medium text-zinc-800 dark:text-zinc-100">{title}</p>
      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{body}</p>
    </div>
  );
}

function LoadingGrid() {
  return (
    <div role="status" aria-label="Loading events" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className="h-64 rounded-2xl bg-gradient-to-r from-zinc-100 via-zinc-200/70 to-zinc-100 bg-[length:200%_100%] animate-shimmer dark:from-zinc-900 dark:via-zinc-800 dark:to-zinc-900"
        />
      ))}
    </div>
  );
}
