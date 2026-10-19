/**
 * Navis runtime client — THE only backend communication layer.
 *
 * Every component, hook, or page that talks to the backend goes through
 * this module. Direct fetch() to backend routes is prohibited.
 *
 * Supports:
 *   * query execution (POST /v2/query, streaming)
 *   * workflow execution (POST /v2/workflow/{name}, streaming)
 *   * provider health (GET /providers/budget)
 *   * voice upload (POST /v2/voice, multipart)
 *   * events (GET /v2/events, GET /v2/events/{id})
 *   * runtime health (GET /health)
 *   * cancellation via AbortSignal
 *
 * Streaming methods return AsyncIterable<RuntimeEvent> and surface
 * malformed lines through an optional callback. Internal event types are
 * rejected by parseRuntimeEvent before they ever reach the caller —
 * invisible orchestration is enforced at this seam.
 */
import { getApiToken } from "./apiToken";
import { getRuntimeConfig } from "./config";
import {
  parseRuntimeEvent,
  type RuntimeEvent,
} from "./events";
import type { CareResponse, NearbyResponse, PlaceDetailsResponse, RouteResponse, TravelMode } from "@/lib/maps/types";
import type { LiveBoardsResponse, LiveVehiclesResponse } from "@/lib/transit/live";
import type {
  EventListing,
  EventsSearchParams,
  EventsSearchResponse,
} from "./listings";
import type {
  GeocodeReverseResponse,
  GeocodeSearchResponse,
  Location,
} from "./location";


export class RuntimeApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "RuntimeApiError";
  }
}


export interface StreamOptions {
  signal?: AbortSignal;
  /** Called for each malformed/forbidden NDJSON line. Stream continues. */
  onMalformed?: (line: string, reason: string) => void;
}


export interface VoiceUploadResult {
  /** "transcribed" | "no_speech". */
  status: string;
  /** Short user-facing message about what the backend did. */
  message: string;
  /** Whisper transcript; "" when status is "no_speech". */
  transcript?: string;
  /** Echoed back so we can verify transport. */
  received_bytes?: number;
  [key: string]: unknown;
}


// ── Internal helpers ────────────────────────────────────────────────────────

function url(endpoint: string): string {
  if (endpoint.startsWith("http")) return endpoint;
  const { apiBaseUrl } = getRuntimeConfig();
  return `${apiBaseUrl}${endpoint}`;
}


/**
 * fetch() for backend calls: adds the signed-in user's API token (costly
 * routes require it in production) and retries once with a fresh token if
 * the backend says it expired.
 */
async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const withToken = async (force: boolean) => {
    const headers = new Headers(init.headers);
    const token = await getApiToken(force);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(input, { ...init, headers });
  };
  const response = await withToken(false);
  if (response.status === 401 && !init.signal?.aborted && !(init.body instanceof ReadableStream)) {
    return withToken(true);
  }
  return response;
}


async function requireOk(response: Response): Promise<Response> {
  if (!response.ok) {
    throw new RuntimeApiError(
      response.status,
      `${response.status} ${response.statusText}`
    );
  }
  return response;
}


async function* readNDJSON(
  response: Response,
  options: StreamOptions
): AsyncIterableIterator<RuntimeEvent> {
  if (!response.body) {
    throw new RuntimeApiError(0, "Response has no readable body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const abortHandler = () => {
    reader.cancel().catch(() => undefined);
  };
  if (options.signal) {
    if (options.signal.aborted) {
      await reader.cancel().catch(() => undefined);
      return;
    }
    options.signal.addEventListener("abort", abortHandler, { once: true });
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        if (buffer.trim().length > 0) {
          const ev = parseLine(buffer, options);
          if (ev) yield ev;
        }
        return;
      }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const ev = parseLine(line, options);
        if (ev) yield ev;
      }
    }
  } finally {
    if (options.signal) {
      options.signal.removeEventListener("abort", abortHandler);
    }
    try {
      reader.releaseLock();
    } catch {
      /* lock may already be released */
    }
  }
}


function parseLine(
  raw: string,
  options: StreamOptions
): RuntimeEvent | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    options.onMalformed?.(raw, "invalid_json");
    return null;
  }
  const event = parseRuntimeEvent(parsed);
  if (!event) {
    options.onMalformed?.(
      raw,
      parsed && typeof parsed === "object" && "event" in (parsed as object)
        ? "unknown_event_type"
        : "missing_event_field"
    );
    return null;
  }
  return event;
}


// ── Public API ──────────────────────────────────────────────────────────────

export const runtimeClient = {
  /**
   * Stream a /v2/query run. Returns an async iterable of validated events.
   * Iterating throws RuntimeApiError on non-2xx response.
   */
  async *queryStream(
    query: string,
    userContext: Record<string, unknown> = {},
    options: StreamOptions = {}
  ): AsyncIterableIterator<RuntimeEvent> {
    const response = await apiFetch(url("/v2/query"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/x-ndjson",
      },
      body: JSON.stringify({ query, user_context: userContext }),
      signal: options.signal,
    });
    await requireOk(response);
    yield* readNDJSON(response, options);
  },

  /**
   * Stream the /today hub: one agent section per domain (weather, events,
   * tech, transit, arrival, money, safety, local know-how) for the user's place.
   */
  async *todayStream(
    userContext: Record<string, unknown> = {},
    options: StreamOptions = {}
  ): AsyncIterableIterator<RuntimeEvent> {
    const response = await apiFetch(url("/v2/today"), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
      body: JSON.stringify({ user_context: userContext }),
      signal: options.signal,
    });
    await requireOk(response);
    yield* readNDJSON(response, options);
  },

  /**
   * Stream a specific workflow by name. Lower-level than queryStream;
   * use when you've already determined which workflow to run.
   */
  async *workflowStream(
    name: string,
    query: string,
    userContext: Record<string, unknown> = {},
    options: StreamOptions = {}
  ): AsyncIterableIterator<RuntimeEvent> {
    const response = await apiFetch(url(`/v2/workflow/${encodeURIComponent(name)}`), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/x-ndjson",
      },
      body: JSON.stringify({ query, user_context: userContext }),
      signal: options.signal,
    });
    await requireOk(response);
    yield* readNDJSON(response, options);
  },

  /**
   * GET /v2/geocode/search. Resolve free text or a "lat,lon" coordinate into
   * ranked canonical Locations (Geoapify primary, Nominatim fallback).
   */
  async geocodeSearch(
    query: string,
    options: {
      limit?: number;
      autocomplete?: boolean;
      signal?: AbortSignal;
      /** Rank results near this point first (usually the user's city). */
      near?: { lat: number; lon: number; city?: string | null } | null;
    } = {}
  ): Promise<Location[]> {
    const params = new URLSearchParams({ text: query });
    if (options.limit) params.set("limit", String(options.limit));
    if (options.autocomplete) params.set("autocomplete", "true");
    if (options.near) {
      params.set("bias_lat", String(options.near.lat));
      params.set("bias_lon", String(options.near.lon));
      if (options.near.city) params.set("city", options.near.city);
    }
    const response = await apiFetch(url(`/v2/geocode/search?${params.toString()}`), {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: options.signal,
    });
    await requireOk(response);
    const data = (await response.json()) as GeocodeSearchResponse;
    return Array.isArray(data.results) ? data.results : [];
  },

  /** GET /v2/events. Events near a place, any source, one shape. */
  async eventsSearch(
    params: EventsSearchParams,
    signal?: AbortSignal
  ): Promise<EventsSearchResponse> {
    const q = new URLSearchParams({ lat: String(params.lat), lon: String(params.lon) });
    if (params.city) q.set("city", params.city);
    if (params.countryCode) q.set("country_code", params.countryCode);
    if (params.country) q.set("country", params.country);
    if (params.region) q.set("region", params.region);
    if (params.category) q.set("category", params.category);
    if (params.dateFrom) q.set("date_from", params.dateFrom);
    if (params.dateTo) q.set("date_to", params.dateTo);
    if (params.keyword) q.set("keyword", params.keyword);
    const response = await apiFetch(url(`/v2/events?${q.toString()}`), {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });
    await requireOk(response);
    return response.json();
  },

  /** GET /v2/maps/nearby. Places of one category around a point. */
  async mapsNearby(
    lat: number,
    lon: number,
    category: string,
    radiusM = 3000,
    signal?: AbortSignal
  ): Promise<NearbyResponse> {
    const q = new URLSearchParams({ lat: String(lat), lon: String(lon), category, radius_m: String(radiusM) });
    const response = await apiFetch(url(`/v2/maps/nearby?${q.toString()}`), { headers: { Accept: "application/json" }, signal });
    await requireOk(response);
    return response.json();
  },

  /** GET /v2/maps/route. Directions with geometry + steps for each mode. */
  async mapsRoute(
    from: { lat: number; lon: number },
    to: { lat: number; lon: number },
    modes: TravelMode[] = ["drive", "walk", "bike", "transit"],
    signal?: AbortSignal
  ): Promise<RouteResponse> {
    const q = new URLSearchParams({
      from_lat: String(from.lat), from_lon: String(from.lon),
      to_lat: String(to.lat), to_lon: String(to.lon), modes: modes.join(","),
    });
    const response = await apiFetch(url(`/v2/maps/route?${q.toString()}`), { headers: { Accept: "application/json" }, signal });
    await requireOk(response);
    return response.json();
  },

  /** GET /v2/maps/place. Details for a shop or landmark tapped on the map. */
  async mapsPlace(lat: number, lon: number, name: string, signal?: AbortSignal): Promise<PlaceDetailsResponse> {
    const q = new URLSearchParams({ lat: String(lat), lon: String(lon), name });
    const response = await apiFetch(url(`/v2/maps/place?${q.toString()}`), { headers: { Accept: "application/json" }, signal });
    await requireOk(response);
    return response.json();
  },

  /** GET /v2/transit/live/boards. Live departure boards for the nearest stops. */
  async liveBoards(lat: number, lon: number, stops = 3, signal?: AbortSignal): Promise<LiveBoardsResponse> {
    const q = new URLSearchParams({ lat: String(lat), lon: String(lon), stops: String(stops) });
    const response = await apiFetch(url(`/v2/transit/live/boards?${q.toString()}`), { headers: { Accept: "application/json" }, signal });
    await requireOk(response);
    return response.json();
  },

  /** GET /v2/transit/live/vehicles. Vehicles moving through a map area. */
  async liveVehicles(
    bounds: { minLat: number; minLon: number; maxLat: number; maxLon: number },
    zoom: number,
    signal?: AbortSignal
  ): Promise<LiveVehiclesResponse> {
    const q = new URLSearchParams({
      min_lat: bounds.minLat.toFixed(4), min_lon: bounds.minLon.toFixed(4),
      max_lat: bounds.maxLat.toFixed(4), max_lon: bounds.maxLon.toFixed(4), zoom: String(Math.round(zoom)),
    });
    const response = await apiFetch(url(`/v2/transit/live/vehicles?${q.toString()}`), { headers: { Accept: "application/json" }, signal });
    await requireOk(response);
    return response.json();
  },

  /** GET /v2/care. Emergency numbers, helplines, nearby care, booking. */
  async care(
    place: { lat: number; lon: number; city?: string | null; countryCode?: string | null; country?: string | null; region?: string | null },
    signal?: AbortSignal
  ): Promise<CareResponse> {
    const q = new URLSearchParams({ lat: String(place.lat), lon: String(place.lon) });
    if (place.city) q.set("city", place.city);
    if (place.countryCode) q.set("country_code", place.countryCode);
    if (place.country) q.set("country", place.country);
    if (place.region) q.set("region", place.region);
    const response = await apiFetch(url(`/v2/care?${q.toString()}`), { headers: { Accept: "application/json" }, signal });
    await requireOk(response);
    return response.json();
  },

  /** GET /v2/events/{id}. Full detail; null when the event is gone. */
  async eventDetail(id: string, signal?: AbortSignal): Promise<EventListing | null> {
    const response = await apiFetch(url(`/v2/events/${encodeURIComponent(id)}`), {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });
    if (response.status === 404) return null;
    await requireOk(response);
    const data = (await response.json()) as { event?: EventListing };
    return data.event ?? null;
  },

  /** GET /v2/geocode/reverse. Resolve a coordinate into a single Location. */
  async geocodeReverse(
    lat: number,
    lon: number,
    signal?: AbortSignal
  ): Promise<Location | null> {
    const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });
    const response = await apiFetch(url(`/v2/geocode/reverse?${params.toString()}`), {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });
    await requireOk(response);
    const data = (await response.json()) as GeocodeReverseResponse;
    return data.result ?? null;
  },

  /** GET /health. Returns the parsed body. Throws on non-2xx or timeout. */
  async getHealth(signal?: AbortSignal): Promise<unknown> {
    const response = await apiFetch(url("/health"), {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });
    await requireOk(response);
    return response.json();
  },

  /** GET /providers/budget. Returns the typed provider map. */
  async getProviderHealth<T = unknown>(signal?: AbortSignal): Promise<T> {
    const response = await apiFetch(url("/providers/budget"), {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });
    await requireOk(response);
    return response.json();
  },

  /**
   * Upload a recorded audio Blob to /v2/voice for transcription. On failure
   * throws RuntimeApiError whose message is the backend's client-safe
   * `detail` when it sent one.
   */
  async voiceUpload(
    audio: Blob,
    signal?: AbortSignal
  ): Promise<VoiceUploadResult> {
    const form = new FormData();
    // Use a sensible filename so backend logs are readable.
    const filename = `voice-${Date.now()}.${extensionFor(audio.type)}`;
    form.append("audio", audio, filename);

    const response = await apiFetch(url("/v2/voice"), {
      method: "POST",
      // NOTE: don't set Content-Type — the browser sets the multipart
      // boundary header itself when body is FormData.
      headers: { Accept: "application/json" },
      body: form,
      signal,
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = (await response.json()) as { detail?: unknown };
        if (typeof body.detail === "string" && body.detail) detail = body.detail;
      } catch {
        /* non-JSON error body — keep the status text */
      }
      throw new RuntimeApiError(response.status, detail);
    }
    return response.json();
  },
};


function extensionFor(mime: string): string {
  if (!mime) return "bin";
  if (mime.includes("webm")) return "webm";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("mp4")) return "mp4";
  if (mime.includes("wav")) return "wav";
  if (mime.includes("mpeg")) return "mp3";
  return "bin";
}


// Backwards-compat re-exports for code that still imports the old shape.
// (After this slice, only `runtimeClient` should be used.)
export const API_BASE_URL_GETTER = (): string => getRuntimeConfig().apiBaseUrl;
