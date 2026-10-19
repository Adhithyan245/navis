/**
 * Google Maps deep links — the single source of truth for real-world
 * navigation across Navis. Every location surface (cards, collections,
 * commute) builds its links here so behavior stays consistent.
 */

/** Open a coordinate as a place pin. */
export function googleMapsPlaceUrl(lat: number, lon: number): string {
  return `https://www.google.com/maps?q=${lat},${lon}`;
}

/** Open turn-by-turn directions to a coordinate (origin defaults to the user). */
export function googleMapsDirectionsUrl(lat: number, lon: number): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`;
}

/** True when both coordinates are finite numbers and thus linkable. */
export function hasCoords(
  lat: number | null | undefined,
  lon: number | null | undefined
): lat is number {
  return typeof lat === "number" && typeof lon === "number" && Number.isFinite(lat) && Number.isFinite(lon);
}
