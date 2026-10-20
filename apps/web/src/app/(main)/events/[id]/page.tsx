"use client";
/**
 * /events/[id] — everything known about one event: exact date and local
 * time (with the venue's timezone), venue and directions, tickets and
 * prices, sale windows, rules, accessibility, and for conferences the
 * call-for-papers and code of conduct. Sign up / get tickets on the
 * organiser's site, and see that you're signed up (components/events/EventSignup).
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  CalendarDays,
  Clock,
  ExternalLink,
  Globe,
  Info,
  MapPin,
  Navigation,
  Ticket,
  Users,
} from "lucide-react";

import { EventSignup } from "@/components/events/EventSignup";
import { Button } from "@/components/ui/button";
import { canSignUp } from "@/lib/events/signup";
import { runtimeClient } from "@/lib/runtime/client";
import {
  formatDistance,
  formatPrice,
  formatTime,
  longDate,
  statusLabel,
} from "@/lib/runtime/event-format";
import { categoryLabel, type EventListing } from "@/lib/runtime/listings";
import { googleMapsDirectionsUrl, googleMapsPlaceUrl, hasCoords } from "@/lib/runtime/maps";
import { cn } from "@/lib/utils";

type State =
  | { status: "loading" }
  | { status: "missing" }
  | { status: "error" }
  | { status: "done"; event: EventListing };

function decodeId(raw: string | string[] | undefined): string {
  const v = Array.isArray(raw) ? raw[0] : raw ?? "";
  try {
    return decodeURIComponent(v);
  } catch {
    return v;
  }
}

export default function EventDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = decodeId(params?.id);
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    runtimeClient
      .eventDetail(id, controller.signal)
      .then((event) => setState(event ? { status: "done", event } : { status: "missing" }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ status: "error" });
      });
    return () => controller.abort();
  }, [id]);

  const back = (
    <button
      type="button"
      onClick={() => (window.history.length > 1 ? router.back() : router.push("/events"))}
      className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
    >
      <ArrowLeft className="size-4" /> All events
    </button>
  );

  if (state.status === "loading") {
    return (
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        {back}
        <div className="h-72 rounded-3xl bg-gradient-to-r from-zinc-100 via-zinc-200/70 to-zinc-100 bg-[length:200%_100%] animate-shimmer dark:from-zinc-900 dark:via-zinc-800 dark:to-zinc-900" />
      </div>
    );
  }

  if (state.status !== "done") {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-4 py-16 text-center">
        <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          {state.status === "missing" ? "This event is no longer listed" : "We couldn't load this event"}
        </p>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {state.status === "missing"
            ? "It may have ended or been removed by the organiser."
            : "Please check your connection and try again."}
        </p>
        <Link href="/events" className="text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400">
          Browse events
        </Link>
      </div>
    );
  }

  const e = state.event;
  const d = (e.detail ?? {}) as Record<string, unknown>;
  const v = e.venue;
  const time = formatTime(e.start_time);
  const price = formatPrice(e);
  const status = statusLabel(e.status);
  const coords = hasCoords(v.lat, v.lon);
  const address = [v.address, v.country].filter(Boolean).join(", ");
  const sales = (d.sales ?? null) as {
    public_start?: string | null;
    public_end?: string | null;
    presales?: Array<{ name?: string; start?: string; end?: string; description?: string; url?: string }>;
  } | null;
  const venueInfo = (d.venue_info ?? null) as Record<string, string | null> | null;
  const performers = (Array.isArray(d.performers) ? (d.performers as string[]) : []).filter(
    (p) => p.trim().toLowerCase() !== e.title.trim().toLowerCase()
  );
  const showSub = e.subcategory && e.subcategory.toLowerCase() !== categoryLabel(e.category).toLowerCase();
  const pleaseNote = typeof d.please_note === "string" && d.please_note !== d.info ? d.please_note : null;
  const topics = Array.isArray(d.topics) ? (d.topics as string[]) : [];
  const ctaLabel = e.source === "ticketmaster" ? "Get tickets" : e.category === "tech" ? "Visit website" : "More info";

  return (
    <article className="mx-auto flex max-w-4xl flex-col gap-6">
      {back}

      <div className="overflow-hidden rounded-3xl border border-zinc-200/80 bg-white/90 shadow-soft dark:border-white/[0.07] dark:bg-zinc-900/70">
        {e.image && (
          // eslint-disable-next-line @next/next/no-img-element -- remote provider images
          <img src={e.image} alt="" className="aspect-[16/7] w-full object-cover" />
        )}
        <div className="flex flex-col gap-4 p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold">
            <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300">
              {categoryLabel(e.category)}
            </span>
            {showSub && (
              <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-zinc-600 dark:bg-white/[0.06] dark:text-zinc-300">
                {e.subcategory}
              </span>
            )}
            {(e.online || e.hybrid) && (
              <span className="inline-flex items-center gap-1 rounded-full bg-indigo-600 px-2.5 py-1 text-white">
                <Globe className="size-3" /> {e.online ? "Online" : "In person + online"}
              </span>
            )}
            {status && (
              <span
                className={cn(
                  "rounded-full px-2.5 py-1",
                  status.tone === "bad"
                    ? "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300"
                    : "bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300"
                )}
              >
                {status.label}
              </span>
            )}
          </div>

          <h1 className="text-2xl font-semibold tracking-[-0.02em] text-zinc-900 sm:text-3xl dark:text-zinc-50">
            {e.title}
          </h1>

          <dl className="grid gap-4 sm:grid-cols-2">
            <Fact icon={CalendarDays} label="Date">
              {longDate(e.start_date)}
              {e.end_date && e.end_date !== e.start_date && <> – {longDate(e.end_date)}</>}
            </Fact>
            <Fact icon={Clock} label="Time">
              {time ? (
                <>
                  {time}
                  {e.timezone && <span className="text-zinc-400"> · {e.timezone.replace(/_/g, " ")} time</span>}
                </>
              ) : e.category === "holiday" ? (
                "All day"
              ) : (
                "Not announced yet. Check the organiser's page"
              )}
            </Fact>
            {!e.online && (v.name || address || v.city) && (
              <Fact icon={MapPin} label="Where">
                {v.name && <span className="block font-medium">{v.name}</span>}
                <span className="block text-zinc-500 dark:text-zinc-400">
                  {address || [v.city, v.country].filter(Boolean).join(", ")}
                </span>
                {formatDistance(e.distance_km) && (
                  <span className="block text-xs text-zinc-400">{formatDistance(e.distance_km)}</span>
                )}
              </Fact>
            )}
            {price && (
              <Fact icon={Ticket} label="Price">
                {price}
                <span className="block text-xs text-zinc-400">Fees may apply. Final price is shown at checkout.</span>
              </Fact>
            )}
          </dl>

          <div className="flex flex-wrap gap-2 pt-1">
            {canSignUp(e) ? (
              <EventSignup event={e} />
            ) : e.url && (
              <a href={e.url} target="_blank" rel="noreferrer noopener">
                <Button size="lg">
                  <Ticket /> {ctaLabel} <ExternalLink className="opacity-70" />
                </Button>
              </a>
            )}
            {coords && (
              <>
                <a href={googleMapsDirectionsUrl(v.lat!, v.lon!)} target="_blank" rel="noreferrer noopener">
                  <Button variant="outline" size="lg">
                    <Navigation /> Directions
                  </Button>
                </a>
                <a href={googleMapsPlaceUrl(v.lat!, v.lon!)} target="_blank" rel="noreferrer noopener">
                  <Button variant="ghost" size="lg">
                    <MapPin /> View on map
                  </Button>
                </a>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Long-form details */}
      <div className="grid gap-4 md:grid-cols-2">
        {performers.length > 0 && (
          <Section icon={Users} title="Lineup">
            <ul className="flex flex-wrap gap-1.5">
              {performers.map((p) => (
                <li key={p} className="rounded-md bg-zinc-100 px-2 py-1 text-[13px] dark:bg-white/[0.06]">
                  {p}
                </li>
              ))}
            </ul>
          </Section>
        )}
        {typeof d.info === "string" && d.info && <Section icon={Info} title="About">{d.info}</Section>}
        {e.summary && e.category === "holiday" && <Section icon={Info} title="Good to know">{e.summary}</Section>}
        {typeof d.local_name === "string" && (
          <Section icon={Globe} title="Local name">
            {d.local_name}
            {Array.isArray(d.regions) && d.regions.length > 0 && (
              <span className="mt-1 block text-zinc-500">Observed in: {(d.regions as string[]).join(", ")}</span>
            )}
          </Section>
        )}
        {pleaseNote && <Section icon={Info} title="Please note">{pleaseNote}</Section>}
        {sales && (sales.public_start || (sales.presales?.length ?? 0) > 0) && (
          <Section icon={Ticket} title="Ticket sales">
            {sales.public_start && (
              <p>
                General sale: {formatInstant(sales.public_start)}
                {sales.public_end && <> until {formatInstant(sales.public_end)}</>}
              </p>
            )}
            {sales.presales && sales.presales.length > 0 && (
              <ul className="mt-2 space-y-1.5">
                {sales.presales.map((p, i) => (
                  <li key={`${p.name}-${i}`} className="text-[13px]">
                    <span className="font-medium">{p.name}</span>
                    {p.start && <span className="text-zinc-500"> · {formatInstant(p.start)}</span>}
                    {p.description && <span className="block text-zinc-500">{p.description}</span>}
                  </li>
                ))}
              </ul>
            )}
          </Section>
        )}
        {(typeof d.age_restriction === "boolean" || typeof d.accessibility === "string" || typeof d.ticket_limit === "string") && (
          <Section icon={Users} title="Access & restrictions">
            {d.age_restriction === true && <p>Age restrictions apply. Bring a valid photo ID.</p>}
            {typeof d.accessibility === "string" && <p>{d.accessibility}</p>}
            {typeof d.ticket_limit === "string" && <p className="text-zinc-500">{d.ticket_limit}</p>}
          </Section>
        )}
        {venueInfo && (venueInfo.parking || venueInfo.box_office || venueInfo.rules || venueInfo.children) && (
          <Section icon={MapPin} title="At the venue">
            {venueInfo.parking && <p><span className="font-medium">Parking:</span> {venueInfo.parking}</p>}
            {venueInfo.box_office && <p className="mt-1"><span className="font-medium">Box office:</span> {venueInfo.box_office}</p>}
            {venueInfo.children && <p className="mt-1"><span className="font-medium">Children:</span> {venueInfo.children}</p>}
            {venueInfo.rules && <p className="mt-1 text-zinc-500">{venueInfo.rules}</p>}
          </Section>
        )}
        {typeof d.seatmap === "string" && (
          <Section icon={Ticket} title="Seat map">
            {/* eslint-disable-next-line @next/next/no-img-element -- remote provider image */}
            <img src={d.seatmap} alt="Venue seat map" className="w-full rounded-lg" loading="lazy" />
          </Section>
        )}
        {(topics.length > 0 || typeof d.cfp_url === "string" || typeof d.code_of_conduct === "string") && (
          <Section icon={Info} title="Conference details">
            {topics.length > 0 && <p>Topics: {topics.join(", ")}</p>}
            {typeof d.languages === "string" && <p className="mt-1">Language: {d.languages}</p>}
            {typeof d.cfp_url === "string" && (
              <p className="mt-1">
                <a href={d.cfp_url} target="_blank" rel="noreferrer noopener" className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                  Call for speakers
                </a>
                {typeof d.cfp_end === "string" && <span className="text-zinc-500"> · closes {longDate(d.cfp_end)}</span>}
              </p>
            )}
            {typeof d.code_of_conduct === "string" && (
              <p className="mt-1">
                <a href={d.code_of_conduct} target="_blank" rel="noreferrer noopener" className="text-indigo-600 hover:underline dark:text-indigo-400">
                  Code of conduct
                </a>
              </p>
            )}
          </Section>
        )}
      </div>

      <p className="text-[11px] text-zinc-400">
        Source: {e.source === "ticketmaster" ? "Ticketmaster" : e.source === "confs.tech" ? "confs.tech" : "Nager.Date public holidays"}.
        Details can change. Confirm with the organiser before you travel.
      </p>
    </article>
  );
}

function formatInstant(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

function Fact({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Clock;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-300">
        <Icon className="size-4" aria-hidden />
      </span>
      <div className="min-w-0 text-sm text-zinc-800 dark:text-zinc-200">
        <dt className="text-xs font-medium uppercase tracking-wide text-zinc-400">{label}</dt>
        <dd className="mt-0.5">{children}</dd>
      </div>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Clock;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200/80 bg-white/90 p-5 text-sm leading-relaxed text-zinc-700 shadow-soft dark:border-white/[0.07] dark:bg-zinc-900/70 dark:text-zinc-300">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        <Icon className="size-4 text-indigo-500" aria-hidden /> {title}
      </h2>
      {children}
    </section>
  );
}
