/**
 * GET /api/geo — the visitor's approximate city from their IP, as the host
 * reports it (Vercel's x-vercel-ip-* headers; empty elsewhere). Used only to
 * rank place search results near the visitor when their profile has no city;
 * never stored.
 */
import { NextResponse, type NextRequest } from "next/server";

function header(request: NextRequest, name: string): string | null {
  const v = request.headers.get(name);
  if (!v) return null;
  try {
    return decodeURIComponent(v);
  } catch {
    return v;
  }
}

export async function GET(request: NextRequest) {
  const lat = Number(header(request, "x-vercel-ip-latitude"));
  const lon = Number(header(request, "x-vercel-ip-longitude"));
  const ok = Number.isFinite(lat) && Number.isFinite(lon) && request.headers.has("x-vercel-ip-latitude");
  const body = ok
    ? { lat, lon, city: header(request, "x-vercel-ip-city"), country: header(request, "x-vercel-ip-country") }
    : {};
  return NextResponse.json(body, { headers: { "Cache-Control": "private, max-age=3600" } });
}
