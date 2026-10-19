/** Display helpers for event listings (dates, times, prices, places). */
import type { EventListing } from "@/lib/runtime/listings";

function parseDay(day: string): Date {
  // "YYYY-MM-DD" as a local calendar day (not UTC midnight).
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

export function toISODay(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

export function addDays(d: Date, n: number): Date {
  const out = new Date(d);
  out.setDate(out.getDate() + n);
  return out;
}

export type DateRangeKey = "today" | "weekend" | "week" | "month" | "quarter";

export const DATE_RANGES: ReadonlyArray<{ key: DateRangeKey; label: string }> = [
  { key: "today", label: "Today" },
  { key: "weekend", label: "This weekend" },
  { key: "week", label: "Next 7 days" },
  { key: "month", label: "Next 30 days" },
  { key: "quarter", label: "Next 3 months" },
];

export function dateRange(key: DateRangeKey, now = new Date()): { from: string; to: string } {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  switch (key) {
    case "today":
      return { from: toISODay(today), to: toISODay(today) };
    case "weekend": {
      const dow = today.getDay(); // 0 Sun … 6 Sat
      if (dow === 0) return { from: toISODay(today), to: toISODay(today) };
      const sat = dow === 6 ? today : addDays(today, 6 - dow);
      const start = dow === 5 ? today : sat; // Friday counts as the weekend
      return { from: toISODay(start), to: toISODay(addDays(sat, 1)) };
    }
    case "week":
      return { from: toISODay(today), to: toISODay(addDays(today, 6)) };
    case "quarter":
      return { from: toISODay(today), to: toISODay(addDays(today, 89)) };
    case "month":
    default:
      return { from: toISODay(today), to: toISODay(addDays(today, 29)) };
  }
}

/** "Today", "Tomorrow", or "Sat, Oct 24". */
export function dayHeading(day: string | null, now = new Date()): string {
  if (!day) return "Date to be announced";
  const today = toISODay(now);
  if (day === today) return "Today";
  if (day === toISODay(addDays(now, 1))) return "Tomorrow";
  return parseDay(day).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    ...(day.slice(0, 4) !== today.slice(0, 4) ? { year: "numeric" } : {}),
  });
}

/** Long form: "Saturday, October 24, 2026". */
export function longDate(day: string | null): string {
  if (!day) return "Date to be announced";
  return parseDay(day).toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

/** "8:00 PM" from a venue-local "20:00:00". */
export function formatTime(time: string | null): string | null {
  if (!time) return null;
  const [h, m] = time.split(":").map(Number);
  if (!Number.isFinite(h)) return null;
  const d = new Date(2000, 0, 1, h, m || 0);
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function formatDateSpan(e: EventListing): string {
  if (e.end_date && e.start_date && e.end_date !== e.start_date) {
    return `${dayHeading(e.start_date)} – ${dayHeading(e.end_date)}`;
  }
  return dayHeading(e.start_date);
}

export function formatPrice(e: EventListing): string | null {
  const p = e.price;
  if (!p || (p.min == null && p.max == null)) return null;
  const fmt = (n: number) => {
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: p.currency || "USD",
        maximumFractionDigits: n % 1 === 0 ? 0 : 2,
      }).format(n);
    } catch {
      return `${n} ${p.currency ?? ""}`.trim();
    }
  };
  if (p.min != null && p.max != null && p.max !== p.min) return `${fmt(p.min)} – ${fmt(p.max)}`;
  return `From ${fmt((p.min ?? p.max) as number)}`;
}

export function placeLine(e: EventListing): string | null {
  const v = e.venue;
  if (e.online) return "Online";
  const where = [v.name, v.city, v.name ? null : v.country].filter(Boolean).join(" · ");
  return where || v.country || null;
}

export function formatDistance(km: number | null): string | null {
  if (km == null) return null;
  return km < 1 ? `${Math.round(km * 1000)} m away` : `${km < 10 ? km.toFixed(1) : Math.round(km)} km away`;
}

export function statusLabel(status: string | null): { label: string; tone: "warn" | "bad" } | null {
  switch (status) {
    case "cancelled":
      return { label: "Cancelled", tone: "bad" };
    case "postponed":
      return { label: "Postponed", tone: "warn" };
    case "rescheduled":
      return { label: "Rescheduled", tone: "warn" };
    case "soldout":
      return { label: "Sold out", tone: "warn" };
    case "waitlist":
      return { label: "Waitlist open", tone: "warn" };
    case "offsale":
      // Ticketmaster: online sales closed (often on the day). Not
      // necessarily sold out; tickets may still be at the door.
      return { label: "Online sales closed", tone: "warn" };
    default:
      return null;
  }
}
