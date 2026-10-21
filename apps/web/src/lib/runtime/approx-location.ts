/**
 * The visitor's approximate city (GET /api/geo), fetched once per session.
 * Only for ranking place search near them when no city is known; null when
 * the host doesn't report one.
 */
export interface ApproxLocation {
  lat: number;
  lon: number;
  city: string | null;
}

const KEY = "navis_approx_location";
let pending: Promise<ApproxLocation | null> | null = null;

function cached(): ApproxLocation | null | undefined {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    return raw === null ? undefined : (JSON.parse(raw) as ApproxLocation | null);
  } catch {
    return undefined;
  }
}

export function approxLocation(): Promise<ApproxLocation | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  const hit = cached();
  if (hit !== undefined) return Promise.resolve(hit);
  pending ??= fetch("/api/geo", { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : {}))
    .then((d: Partial<ApproxLocation>) => {
      const loc = typeof d.lat === "number" && typeof d.lon === "number" ? { lat: d.lat, lon: d.lon, city: d.city ?? null } : null;
      try {
        window.sessionStorage.setItem(KEY, JSON.stringify(loc));
      } catch {
        /* storage disabled */
      }
      return loc;
    })
    .catch(() => null);
  return pending;
}
