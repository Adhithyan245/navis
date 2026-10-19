/**
 * Canonical Location types — the frontend mirror of the backend
 * `apps/api/models/location.py` Location model. Every geocoding result
 * (Geoapify primary, Nominatim fallback) is normalized to this shape on the
 * server, so the client only ever deals with one location representation.
 */

/** Coarse-to-fine place categories. Mirrors backend LOCATION_TYPES. */
export type LocationType =
  | "country"
  | "region"
  | "county"
  | "city"
  | "district"
  | "suburb"
  | "neighborhood"
  | "street"
  | "postcode"
  | "landmark"
  | "address"
  | "coordinate"
  | "place"
  | "unknown";

/** Lightweight per-candidate commute leg (Phase 4). Mirrors backend CommuteSummary. */
export interface CommuteSummary {
  mode: string;
  durationMinutes: number;
  distanceKm: number;
}

export interface Location {
  id: string;
  type: LocationType;
  name: string;
  label: string;
  lat: number;
  lon: number;
  bbox?: number[] | null;
  country?: string | null;
  country_code?: string | null;
  region?: string | null;
  city?: string | null;
  district?: string | null;
  suburb?: string | null;
  postcode?: string | null;
  provider: string;
  confidence: number;
  // ── Optional enrichment (Phase 3B). Absent fields degrade gracefully. ──
  state?: string | null;
  short_description?: string | null;
  population?: number | null;
  tags?: string[];
  // Commute summaries to the user's office, attached by neighborhood_match
  // when an office location is available (Phase 4). Absent otherwise.
  commutes?: CommuteSummary[];
  raw?: Record<string, unknown>;
}

/** GET /v2/geocode/search response. */
export interface GeocodeSearchResponse {
  results: Location[];
}

/** GET /v2/geocode/reverse response. */
export interface GeocodeReverseResponse {
  result: Location | null;
}

/** Minimal runtime guard for an arbitrary parsed value. */
export function isLocation(value: unknown): value is Location {
  if (!value || typeof value !== "object") return false;
  const o = value as Record<string, unknown>;
  return (
    typeof o.id === "string" &&
    typeof o.name === "string" &&
    typeof o.label === "string" &&
    typeof o.lat === "number" &&
    typeof o.lon === "number" &&
    typeof o.provider === "string"
  );
}
