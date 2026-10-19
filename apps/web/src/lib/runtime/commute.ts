/**
 * Commute types — frontend mirror of the backend CommuteEstimate model
 * (apps/api/models/commute.py). One origin→destination travel estimate for a
 * single mode. The wire shape is camelCase, matching this interface directly.
 */
import { isLocation, type Location } from "./location";

export type CommuteMode = "driving" | "walking" | "cycling";

export interface Commute {
  origin: Location;
  destination: Location;
  distanceKm: number;
  durationMinutes: number;
  mode: string;
  provider: string;
  confidence: number;
}

export function isCommute(value: unknown): value is Commute {
  if (!value || typeof value !== "object") return false;
  const o = value as Record<string, unknown>;
  return (
    typeof o.distanceKm === "number" &&
    typeof o.durationMinutes === "number" &&
    typeof o.mode === "string" &&
    typeof o.provider === "string" &&
    isLocation(o.origin) &&
    isLocation(o.destination)
  );
}
