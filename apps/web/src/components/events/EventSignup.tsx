"use client";
/**
 * Sign up for an event. Registration happens on the organiser's site, so
 * "Sign up" opens it and then asks whether the user finished; "Yes" marks
 * the event signed up on their account (synced, reminded). Events with no
 * organiser link get a direct "I'm going". Signed up: a badge, add to
 * calendar, and undo.
 */
import { useEffect, useRef, useState } from "react";
import { CalendarPlus, Check, CircleCheck, ExternalLink, Ticket } from "lucide-react";

import { Button } from "@/components/ui/button";
import { canSignUp, downloadIcs, listingToSavedEvent, organiserSite, usesTickets } from "@/lib/events/signup";
import type { EventListing } from "@/lib/runtime/listings";
import { useSavedItemsContext } from "@/lib/saved/context";
import { cn } from "@/lib/utils";

const PENDING_KEY = "navis_signup_pending";

function readPending(id: string): boolean {
  try {
    return window.sessionStorage.getItem(PENDING_KEY) === id;
  } catch {
    return false;
  }
}

function writePending(id: string | null) {
  try {
    if (id) window.sessionStorage.setItem(PENDING_KEY, id);
    else window.sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* storage disabled */
  }
}

export function EventSignup({ event }: { event: EventListing }) {
  const { state, ready, setEventSignedUp } = useSavedItemsContext();
  const saved = state.savedEvents.find((s) => s.id === event.id);
  const signedUp = !!saved?.signedUp;
  // Survives a reload after coming back from the organiser's tab.
  const [asking, setAsking] = useState(() => typeof window !== "undefined" && readPending(event.id));

  const promptRef = useRef<HTMLDivElement | null>(null);
  const [nudge, setNudge] = useState(false);

  // Coming back from the organiser's tab: put the question in front of them.
  useEffect(() => {
    if (!asking) return;
    const onReturn = () => {
      if (document.visibilityState !== "visible") return;
      promptRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      setNudge(true);
      setTimeout(() => setNudge(false), 1800);
    };
    document.addEventListener("visibilitychange", onReturn);
    window.addEventListener("focus", onReturn);
    return () => {
      document.removeEventListener("visibilitychange", onReturn);
      window.removeEventListener("focus", onReturn);
    };
  }, [asking]);

  const tickets = usesTickets(event);
  const site = organiserSite(event);
  const open = canSignUp(event);

  const confirm = (yes: boolean) => {
    writePending(null);
    setAsking(false);
    if (yes) setEventSignedUp(listingToSavedEvent(event), true);
  };

  if (!ready) return null;

  if (signedUp) {
    const when = saved?.signedUpAt
      ? new Date(saved.signedUpAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })
      : null;
    return (
      <div className="flex w-full flex-col gap-3 rounded-2xl border border-emerald-200 bg-emerald-50/80 p-4 dark:border-emerald-400/20 dark:bg-emerald-500/10">
        <p className="flex items-center gap-2 text-sm font-semibold text-emerald-800 dark:text-emerald-200">
          <CircleCheck className="size-5" aria-hidden />
          {tickets ? "You have tickets" : "You're signed up"}
          {when && <span className="font-normal text-emerald-700/80 dark:text-emerald-300/80">· since {when}</span>}
        </p>
        <p className="text-[13px] text-emerald-900/80 dark:text-emerald-100/80">
          It&apos;s in your events and on all your devices. If notifications are on, we&apos;ll remind you the day before.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => downloadIcs(event)}>
            <CalendarPlus /> Add to calendar
          </Button>
          {event.url && (
            <a href={event.url} target="_blank" rel="noreferrer noopener">
              <Button size="sm" variant="ghost">
                {tickets ? "View on Ticketmaster" : `Open on ${site}`} <ExternalLink className="opacity-70" />
              </Button>
            </a>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setEventSignedUp(saved!, false)}
            className="text-zinc-500"
          >
            I&apos;m not going
          </Button>
        </div>
        <p className="text-[11px] text-emerald-900/60 dark:text-emerald-100/60">
          This only updates Navis. To cancel a registration or ticket, use {site}.
        </p>
      </div>
    );
  }

  if (!open) return null;

  if (asking) {
    return (
      <div
        ref={promptRef}
        role="alertdialog"
        aria-label="Confirm sign-up"
        className={cn(
          "flex w-full flex-col gap-3 rounded-2xl border-2 border-indigo-400 bg-indigo-50 p-4 shadow-lg transition-shadow dark:border-indigo-400/60 dark:bg-indigo-500/15",
          nudge && "ring-4 ring-indigo-300/70 dark:ring-indigo-400/40"
        )}
      >
        <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-300">
          One more step
        </p>
        <p className="-mt-2 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          {tickets ? `Did you get your tickets on ${site}?` : `Did you finish signing up on ${site}?`}
        </p>
        <p className="text-[13px] text-zinc-600 dark:text-zinc-300">
          Tap yes and Navis marks it on your account, so it shows in My events and you get a reminder.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => confirm(true)}>
            <Check /> {tickets ? "Yes, I have tickets" : "Yes, I'm signed up"}
          </Button>
          <Button size="sm" variant="outline" onClick={() => confirm(false)}>
            Not yet
          </Button>
          {event.url && (
            <a href={event.url} target="_blank" rel="noreferrer noopener">
              <Button size="sm" variant="ghost">
                Open {site} again <ExternalLink className="opacity-70" />
              </Button>
            </a>
          )}
        </div>
      </div>
    );
  }

  if (!event.url) {
    return (
      <Button size="lg" onClick={() => setEventSignedUp(listingToSavedEvent(event), true)}>
        <Check /> I&apos;m going
      </Button>
    );
  }

  return (
    <a
      href={event.url}
      target="_blank"
      rel="noreferrer noopener"
      onClick={() => {
        writePending(event.id);
        setAsking(true);
      }}
    >
      <Button size="lg">
        <Ticket /> {tickets ? "Get tickets" : "Sign up"} <ExternalLink className="opacity-70" />
      </Button>
    </a>
  );
}
