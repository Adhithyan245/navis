/**
 * Event listings from GET /v2/events (Ticketmaster, confs.tech, public
 * holidays — normalized to one shape by the backend's EventsService).
 */

export const EVENT_CATEGORIES = [
  { value: "music", label: "Music" },
  { value: "sports", label: "Sports" },
  { value: "arts", label: "Arts & theatre" },
  { value: "comedy", label: "Comedy" },
  { value: "family", label: "Family" },
  { value: "film", label: "Film" },
  { value: "tech", label: "Tech & meetups" },
  { value: "community", label: "Community" },
  { value: "holiday", label: "Holidays" },
] as const;

export type EventCategory = (typeof EVENT_CATEGORIES)[number]["value"];

export interface EventVenue {
  name: string | null;
  address: string | null;
  city: string | null;
  region: string | null;
  country: string | null;
  country_code: string | null;
  postcode: string | null;
  lat: number | null;
  lon: number | null;
}

export interface EventPrice {
  min: number | null;
  max: number | null;
  currency: string | null;
}

export interface EventListing {
  id: string;
  source: "ticketmaster" | "confs.tech" | "nager.date" | string;
  title: string;
  category: EventCategory | string;
  subcategory: string | null;
  start_date: string | null;
  /** Local time at the venue, "HH:MM:SS"; null when not announced. */
  start_time: string | null;
  start_utc: string | null;
  end_date: string | null;
  timezone: string | null;
  status: string | null;
  online: boolean;
  hybrid?: boolean;
  venue: EventVenue;
  distance_km: number | null;
  url: string | null;
  image: string | null;
  price: EventPrice | null;
  summary: string | null;
  /** confs.tech only: how the conference relates to the searched place. */
  locality?: "city" | "country" | "online" | "elsewhere" | null;
  detail?: Record<string, unknown>;
}

export interface EventsSearchResponse {
  events: EventListing[];
  counts: Record<string, number>;
  window: { from: string; to: string };
  radius_km: number | null;
  sources: string[];
  coverage_note: string | null;
}

export interface EventsSearchParams {
  lat: number;
  lon: number;
  city?: string | null;
  countryCode?: string | null;
  country?: string | null;
  region?: string | null;
  category?: EventCategory | null;
  dateFrom?: string;
  dateTo?: string;
  keyword?: string;
}

export function categoryLabel(value: string): string {
  return EVENT_CATEGORIES.find((c) => c.value === value)?.label ?? value;
}
