/**
 * Live transit: shapes from /v2/transit/live/* and helpers to animate
 * vehicles. The API sends each moving vehicle as a path segment between two
 * stops with departure/arrival times; positions in between are interpolated
 * along the path by distance.
 */
export interface LiveDeparture {
  line: string;
  mode: string;
  headsign: string | null;
  color: string | null;
  text_color: string | null;
  agency: string | null;
  departure: string;
  scheduled: string | null;
  delay_min: number | null;
  realtime: boolean;
  cancelled: boolean;
  platform: string | null;
  route_url: string | null;
  trip_id?: string | null;
}

export interface LiveStopBoard {
  stop_id: string;
  name: string;
  lat: number;
  lon: number;
  distance_m: number;
  modes: string[];
  timezone: string | null;
  departures: LiveDeparture[];
  live: boolean;
}

export interface LiveBoardsResponse {
  stops: LiveStopBoard[];
  message: string | null;
}

export interface LiveVehicle {
  id: string;
  line: string;
  mode: string;
  color: string;
  headsign: string | null;
  from: string | null;
  to: string | null;
  departure: string;
  arrival: string;
  delay_min: number | null;
  realtime: boolean;
  path: [number, number][];
}

export interface LiveVehiclesResponse {
  vehicles: LiveVehicle[];
  server_time?: string;
  message: string | null;
  too_wide?: boolean;
}

export interface LiveTripStop {
  name: string;
  stop_id: string | null;
  lat: number;
  lon: number;
  arrival: string;
  departure: string;
  scheduled: string | null;
  delay_min: number | null;
  cancelled: boolean;
  passed: boolean;
  minutes: number | null;
  yours: boolean;
}

/** One vehicle's trip (GET /v2/transit/live/trip). `vehicle` is a moving
 * segment to animate, or a fixed position while it waits at a stop. */
export interface LiveTrip {
  trip_id: string;
  line?: string;
  mode?: string;
  headsign?: string | null;
  color?: string;
  text_color?: string | null;
  agency?: string | null;
  realtime?: boolean;
  cancelled?: boolean;
  stops: LiveTripStop[];
  vehicle:
    | { from: string; to: string; departure: string; arrival: string; path: [number, number][] }
    | { position: [number, number]; at: string }
    | null;
  path: [number, number][];
  your_stop: { name: string; arrival: string; delay_min: number | null; minutes: number | null; stops_away: number } | null;
  server_time?: string;
  message: string | null;
}

/** What to track: a trip, optionally from the rider's stop and departure. */
export interface TrackTarget {
  tripId: string;
  stopId?: string | null;
  stopName?: string | null;
  at?: string | null;
}

export function trackHref(t: TrackTarget, near?: { lat: number; lon: number }): string {
  const q = new URLSearchParams({ track: t.tripId, live: "1" });
  if (t.stopId) q.set("stop_id", t.stopId);
  if (t.stopName) q.set("stop_name", t.stopName);
  if (t.at) q.set("at", t.at);
  if (near) {
    q.set("tlat", String(near.lat));
    q.set("tlon", String(near.lon));
  }
  return `/maps?${q.toString()}`;
}

/** A vehicle segment prepared for fast interpolation. */
export interface Track extends LiveVehicle {
  t0: number;
  t1: number;
  cumulative: number[];
  length: number;
}

function haversine(a: [number, number], b: [number, number]): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b[1] - a[1]);
  const dLon = toRad(b[0] - a[0]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.sqrt(h));
}

export function toTrack(v: LiveVehicle): Track {
  const cumulative = [0];
  for (let i = 1; i < v.path.length; i++) cumulative.push(cumulative[i - 1] + haversine(v.path[i - 1], v.path[i]));
  return { ...v, t0: Date.parse(v.departure), t1: Date.parse(v.arrival), cumulative, length: cumulative[cumulative.length - 1] };
}

/** Position at time `now` (ms), or null when the vehicle isn't on this segment then. */
export function positionAt(track: Track, now: number): [number, number] | null {
  if (now < track.t0 || now > track.t1) return null;
  const span = track.t1 - track.t0;
  const target = span > 0 ? ((now - track.t0) / span) * track.length : track.length;
  const c = track.cumulative;
  let i = 1;
  while (i < c.length && c[i] < target) i++;
  if (i >= c.length) return track.path[track.path.length - 1];
  const seg = c[i] - c[i - 1];
  const f = seg > 0 ? (target - c[i - 1]) / seg : 0;
  const [x0, y0] = track.path[i - 1];
  const [x1, y1] = track.path[i];
  return [x0 + (x1 - x0) * f, y0 + (y1 - y0) * f];
}

export function minutesUntil(iso: string, now = Date.now()): number {
  return Math.round((Date.parse(iso) - now) / 60_000);
}

export function clock(iso: string, timeZone?: string | null): string {
  try {
    return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", ...(timeZone ? { timeZone } : {}) });
  } catch {
    return "";
  }
}

export function isTransitPlace(categories: string[] | undefined, name?: string): boolean {
  const text = `${(categories ?? []).join(" ")} ${name ?? ""}`.toLowerCase();
  return /(public_transport|railway|station|subway|tram|bus|ferry|metro|train|light rail|halt)/.test(text);
}
