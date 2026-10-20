/**
 * Saved items — places, events, neighborhoods, and canonical locations the
 * user has bookmarked.
 *
 * Stored entirely in localStorage under `navis_saved_items_v1`. The
 * discriminated `kind` field keeps the shape future-extensible. Phase 3B adds
 * the canonical `location` kind: any workflow producing a `Location` can save
 * it directly with no schema change, which is what powers the unified
 * /locations collection.
 */
import type { Location } from "@/lib/runtime/location";

export type SavedItemKind = "place" | "event" | "neighborhood" | "location";

export interface SavedPlace {
  kind: "place";
  id: string;
  title: string;
  city?: string;
  area?: string;
  lat?: number;
  lon?: number;
  url?: string;
  savedAt: number;          // Unix milliseconds
  source?: string;          // provider hint ("foursquare", "geoapify", "ticketmaster", ...)
}

export interface SavedEvent {
  kind: "event";
  id: string;
  title: string;
  venue?: string;
  city?: string;
  url?: string;
  startsAt?: string;        // ISO 8601; without an offset it's the venue's local time
  endsAt?: string;          // ISO 8601 date or date-time
  timezone?: string;        // venue's IANA timezone, when known
  online?: boolean;
  savedAt: number;
  source?: string;
  /** The user signed up / got tickets (confirmed by them after visiting the organiser's page). */
  signedUp?: boolean;
  signedUpAt?: number;      // Unix milliseconds
  /** The full listing when they signed up, so its page still opens after the source drops it. */
  listing?: Record<string, unknown>;
}

export interface SavedNeighborhood {
  kind: "neighborhood";
  id: string;
  title: string;
  city: string;
  area?: string;
  savedAt: number;
}

/**
 * Canonical saved location — the unified shape any location-producing
 * workflow (neighborhood_match, city_explorer, future recommenders) saves.
 * Mirrors the runtime Location's display-relevant fields plus savedAt.
 */
export interface SavedLocation {
  kind: "location";
  id: string;
  label: string;
  type: string;             // canonical Location type ("suburb", "landmark", ...)
  city?: string;
  state?: string;
  country?: string;
  lat?: number;
  lon?: number;
  tags?: string[];
  savedAt: number;
}

export type SavedItem =
  | SavedPlace
  | SavedEvent
  | SavedNeighborhood
  | SavedLocation;

export interface SavedItemsState {
  savedPlaces: SavedPlace[];
  savedEvents: SavedEvent[];
  savedNeighborhoods: SavedNeighborhood[];
  savedLocations: SavedLocation[];
}

export const EMPTY_SAVED: SavedItemsState = {
  savedPlaces: [],
  savedEvents: [],
  savedNeighborhoods: [],
  savedLocations: [],
};

/**
 * Convert a runtime Location into a SavedLocation. `savedAt` is stamped at
 * save time by SaveButton, so this returns 0 as a placeholder.
 */
export function locationToSaved(loc: Location): SavedLocation {
  return {
    kind: "location",
    id: loc.id,
    label: loc.name || loc.label,
    type: loc.type,
    city: loc.city ?? undefined,
    state: (loc.state ?? loc.region) ?? undefined,
    country: loc.country ?? undefined,
    lat: typeof loc.lat === "number" ? loc.lat : undefined,
    lon: typeof loc.lon === "number" ? loc.lon : undefined,
    tags: loc.tags ?? [],
    savedAt: 0,
  };
}
