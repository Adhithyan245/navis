"use client";
/**
 * EventListingCard — one event in the /events grid. Links to the detail page,
 * and shows "Signed up" when the user has signed up for it.
 */
import Link from "next/link";
import {
  CalendarDays,
  CircleCheck,
  Clapperboard,
  Cpu,
  Drama,
  Laugh,
  MapPin,
  Music,
  PartyPopper,
  Trophy,
  Users,
  Baby,
  Globe,
} from "lucide-react";

import type { EventListing } from "@/lib/runtime/listings";
import { categoryLabel } from "@/lib/runtime/listings";
import {
  formatDistance,
  formatPrice,
  formatTime,
  placeLine,
  statusLabel,
} from "@/lib/runtime/event-format";
import { useSavedItemsContext } from "@/lib/saved/context";
import { cn } from "@/lib/utils";

const ICONS: Record<string, typeof Music> = {
  music: Music,
  sports: Trophy,
  arts: Drama,
  comedy: Laugh,
  family: Baby,
  film: Clapperboard,
  tech: Cpu,
  community: Users,
  holiday: PartyPopper,
};

// Gradient backdrops for events without an image, one per category.
const TINTS: Record<string, string> = {
  music: "from-fuchsia-500/80 to-indigo-600/80",
  sports: "from-emerald-500/80 to-teal-600/80",
  arts: "from-rose-500/80 to-orange-500/80",
  comedy: "from-amber-400/80 to-orange-500/80",
  family: "from-sky-400/80 to-indigo-500/80",
  film: "from-zinc-600/80 to-zinc-900/80",
  tech: "from-indigo-500/80 to-cyan-500/80",
  community: "from-violet-500/80 to-purple-600/80",
  holiday: "from-amber-500/80 to-rose-500/80",
};

export function eventHref(id: string): string {
  return `/events/${encodeURIComponent(id)}`;
}

export function EventListingCard({
  event,
  moreTimes = 0,
}: {
  event: EventListing;
  /** Other sessions of the same event that day (collapsed into this card). */
  moreTimes?: number;
}) {
  const Icon = ICONS[event.category] ?? CalendarDays;
  const time = formatTime(event.start_time);
  const price = formatPrice(event);
  const place = placeLine(event);
  const distance = formatDistance(event.distance_km);
  const status = statusLabel(event.status);
  const multiDay = event.end_date && event.start_date && event.end_date !== event.start_date;
  const { state } = useSavedItemsContext();
  const signedUp = state.savedEvents.some((s) => s.id === event.id && s.signedUp);

  return (
    <Link
      href={eventHref(event.id)}
      className="group flex h-full flex-col overflow-hidden rounded-2xl border border-zinc-200/80 bg-white/90 shadow-soft outline-none transition-all duration-300 hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-glow focus-visible:ring-2 focus-visible:ring-indigo-400 dark:border-white/[0.07] dark:bg-zinc-900/70 dark:hover:border-indigo-400/25"
    >
      <div className="relative aspect-[16/8] w-full overflow-hidden">
        {event.image ? (
          // eslint-disable-next-line @next/next/no-img-element -- remote provider images
          <img
            src={event.image}
            alt=""
            loading="lazy"
            className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
          />
        ) : (
          <div
            className={cn(
              "flex size-full items-center justify-center bg-gradient-to-br",
              TINTS[event.category] ?? "from-indigo-500/80 to-fuchsia-500/80"
            )}
          >
            <Icon className="size-10 text-white/85" aria-hidden />
          </div>
        )}
        <span className="absolute left-3 top-3 inline-flex items-center gap-1 rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-semibold text-zinc-800 shadow-sm backdrop-blur dark:bg-zinc-900/85 dark:text-zinc-100">
          <Icon className="size-3" aria-hidden />
          {categoryLabel(event.category)}
        </span>
        {signedUp && (
          <span className="absolute bottom-3 left-3 inline-flex items-center gap-1 rounded-full bg-emerald-600 px-2.5 py-1 text-[11px] font-semibold text-white shadow-sm">
            <CircleCheck className="size-3" aria-hidden />
            {event.source === "ticketmaster" ? "You have tickets" : "Signed up"}
          </span>
        )}
        {(event.online || event.hybrid) && (
          <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-indigo-600/90 px-2.5 py-1 text-[11px] font-semibold text-white shadow-sm">
            <Globe className="size-3" aria-hidden />
            {event.online ? "Online" : "Hybrid"}
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-1.5 p-4">
        <p className="text-[12px] font-medium text-indigo-600 dark:text-indigo-300">
          {time ?? (multiDay ? "Multi-day" : event.category === "holiday" ? "All day" : "Time TBA")}
          {moreTimes > 0 && <span className="text-zinc-500"> +{moreTimes} more {moreTimes === 1 ? "time" : "times"}</span>}
          {event.subcategory && event.subcategory.toLowerCase() !== categoryLabel(event.category).toLowerCase() ? (
            <span className="text-zinc-400 dark:text-zinc-500"> · {event.subcategory}</span>
          ) : null}
        </p>
        <h3 className="line-clamp-2 text-[15px] font-semibold leading-snug tracking-tight text-zinc-900 group-hover:text-indigo-700 dark:text-zinc-50 dark:group-hover:text-indigo-300">
          {event.title}
        </h3>
        {place && (
          <p className="flex min-w-0 items-center gap-1 text-[13px] text-zinc-500 dark:text-zinc-400">
            <MapPin className="size-3.5 shrink-0" aria-hidden />
            <span className="truncate">{place}</span>
          </p>
        )}
        {event.summary && event.category === "holiday" && (
          <p className="text-[12px] text-zinc-500 dark:text-zinc-400">{event.summary}</p>
        )}
        <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 pt-2 text-[12px] text-zinc-500 dark:text-zinc-400">
          {price && <span className="font-medium text-zinc-700 dark:text-zinc-200">{price}</span>}
          {distance && <span>{distance}</span>}
          {status && (
            <span
              className={cn(
                "rounded-md px-1.5 py-0.5 font-medium",
                status.tone === "bad"
                  ? "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300"
                  : "bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300"
              )}
            >
              {status.label}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
