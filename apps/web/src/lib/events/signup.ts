/**
 * Event sign-up helpers. Registration and tickets happen on the organiser's
 * site (Ticketmaster, Luma, Devpost…); Navis records that the user signed
 * up, on their account (SavedEvent.signedUp), once they confirm it.
 */
import type { EventListing } from "@/lib/runtime/listings";
import type { SavedEvent } from "@/lib/saved/schema";

const SITE_NAMES: Record<string, string> = {
  ticketmaster: "Ticketmaster",
  luma: "Luma",
  devpost: "Devpost",
  mlh: "MLH",
  devevents: "dev.events",
  "confs.tech": "the conference website",
};

/** Where the user signs up, for button and prompt copy. */
export function organiserSite(e: Pick<EventListing, "source">): string {
  return SITE_NAMES[e.source] ?? "the organiser's page";
}

export function usesTickets(e: Pick<EventListing, "source">): boolean {
  return e.source === "ticketmaster";
}

/** Holidays aren't attended; ended events can't be signed up for. */
export function canSignUp(e: EventListing, now = Date.now()): boolean {
  if (e.category === "holiday" || e.status === "cancelled") return false;
  const end = e.end_date ?? e.start_date;
  if (end && Date.parse(`${end}T23:59:59`) < now - 24 * 3600_000) return false;
  return true;
}

/** Venue-local start, "YYYY-MM-DDTHH:MM:SS" (no offset), or the UTC instant when that's all we have. */
function startsAt(e: EventListing): string | undefined {
  if (e.start_date && e.start_time) return `${e.start_date}T${e.start_time.length === 5 ? `${e.start_time}:00` : e.start_time}`;
  if (e.start_utc) return e.start_utc;
  return e.start_date ?? undefined;
}

export function listingToSavedEvent(e: EventListing): SavedEvent {
  return {
    kind: "event",
    id: e.id,
    title: e.title,
    venue: e.online ? "Online" : e.venue.name ?? undefined,
    city: e.venue.city ?? undefined,
    url: e.url ?? undefined,
    startsAt: startsAt(e),
    endsAt: e.end_date ?? undefined,
    timezone: e.timezone ?? undefined,
    online: e.online,
    savedAt: 0,
    source: e.source,
    listing: e as unknown as Record<string, unknown>,
  };
}

// ── calendar file (.ics) ───────────────────────────────────────────────────

function icsText(v: string): string {
  return v.replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/([,;])/g, "\\$1");
}

function icsDate(d: string): string {
  return d.slice(0, 10).replace(/-/g, "");
}

function icsUtc(iso: string): string {
  return new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

/** An iCalendar event for "Add to calendar". Timed events use the UTC
 * instant when known, else the venue's local time and timezone. */
export function eventIcs(e: EventListing, appUrl: string): string {
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Navis//Events//EN", "BEGIN:VEVENT"];
  lines.push(`UID:${icsText(e.id)}@navis`);
  lines.push(`DTSTAMP:${icsUtc(new Date().toISOString())}`);
  if (e.start_utc && e.start_time) {
    lines.push(`DTSTART:${icsUtc(e.start_utc)}`);
    lines.push(`DTEND:${icsUtc(new Date(Date.parse(e.start_utc) + 2 * 3600_000).toISOString())}`);
  } else if (e.start_date && e.start_time && e.timezone) {
    const local = `${icsDate(e.start_date)}T${e.start_time.replace(/:/g, "").padEnd(6, "0").slice(0, 6)}`;
    lines.push(`DTSTART;TZID=${e.timezone}:${local}`);
  } else if (e.start_date) {
    const end = new Date(`${(e.end_date ?? e.start_date).slice(0, 10)}T00:00:00Z`);
    end.setUTCDate(end.getUTCDate() + 1);
    lines.push(`DTSTART;VALUE=DATE:${icsDate(e.start_date)}`);
    lines.push(`DTEND;VALUE=DATE:${icsDate(end.toISOString())}`);
  }
  lines.push(`SUMMARY:${icsText(e.title)}`);
  const where = e.online ? "Online" : [e.venue.name, e.venue.address, e.venue.city].filter(Boolean).join(", ");
  if (where) lines.push(`LOCATION:${icsText(where)}`);
  const link = e.url ?? `${appUrl}/events/${encodeURIComponent(e.id)}`;
  lines.push(`URL:${icsText(link)}`);
  lines.push(`DESCRIPTION:${icsText(`Details: ${link}`)}`);
  lines.push("END:VEVENT", "END:VCALENDAR");
  return lines.join("\r\n");
}

export function downloadIcs(e: EventListing): void {
  const blob = new Blob([eventIcs(e, window.location.origin)], { type: "text/calendar;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${e.title.replace(/[^\w\- ]+/g, "").trim().slice(0, 60) || "event"}.ics`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
