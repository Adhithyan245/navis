/**
 * Wire contract — exactly what the backend's view translator emits.
 *
 * Source of truth: apps/api/runtime/view.py
 *
 * The runtime emits a large set of *internal* events (workflow_started,
 * node_started/completed/failed, provider_fallback, etc.) but those are
 * filtered out by the view translator. ONLY the events listed in this
 * file ever cross the wire. The frontend should NEVER attempt to handle
 * an internal event type — if one appears, it's a backend bug.
 */

/** Result section from a single workflow inside a composed run. */
export type SectionStatus = "ok" | "partial" | "empty" | "unavailable";

export interface RuntimeSection {
  /** Category label, never the workflow id ("places" | "events" | "work" | ...). */
  kind: string;
  /** Whatever shape the workflow's terminal stream produced. */
  data: unknown;
  /** Present on agent sections (multi-agent answers and the /today hub). */
  agent?: string;
  title?: string;
  status?: SectionStatus;
  /** User-facing, always positive: what's there, or what to try instead. */
  message?: string;
  alternatives?: string[];
}

/** Per-place item shape — matches what fusion+ranking emit for explore/work. */
export interface PlaceItem {
  /** Top-level name. Foursquare/Ticketmaster venues; absent on Geoapify Features. */
  name?: string;
  rating?: number;
  price_level?: number;
  open_now?: boolean;
  types?: string[];
  location?: { lat: number; lng?: number; lon?: number };
  /** Geoapify GeoJSON Feature shape — name + coords nested under properties. */
  properties?: {
    name?: string;
    formatted?: string;
    lat?: number;
    lon?: number;
    categories?: string[];
    place_id?: string;
    [k: string]: unknown;
  };
  rationale?: Record<string, unknown>;
  _provenance?: { provider: string; confidence: number; verified?: boolean };
  [key: string]: unknown;
}

/** Per-event item shape — matches what connect_mode emits. */
export interface EventItem {
  title?: string;
  /** Ticketmaster uses `name`, not `title`. Most events you'll see in the wild. */
  name?: string;
  id?: string;
  url?: string;
  categories?: string[];
  /** Ticketmaster nested-categories shape. */
  classifications?: Array<{
    primary?: boolean;
    segment?: { name?: string };
    genre?: { name?: string };
    subGenre?: { name?: string };
  }>;
  /** Ticketmaster venue payload. */
  _embedded?: {
    venues?: Array<{
      name?: string;
      city?: { name?: string };
      location?: { latitude?: string | number; longitude?: string | number };
    }>;
  };
  dates?: {
    start?: { localDate?: string; localTime?: string; dateTime?: string };
  };
  rationale?: Record<string, unknown>;
  _provenance?: { provider: string; confidence: number; verified?: boolean };
  [key: string]: unknown;
}

/** Knowledge chunk view returned by ContextRetrievalNode. */
export interface KnowledgeChunk {
  path: string;
  city: string | null;
  workflow: string | null;
  tags: string[];
  priority: number;
  body: string;
}

/** Final payload for single-workflow runs (e.g. /v2/workflow/explore_city). */
export interface FinalSingleWorkflowPayload {
  query: string;
  summary?: string | null;
  location?: { lat: number; lon?: number; lng?: number; name?: string };
  results?: Array<PlaceItem | EventItem>;
  context?: KnowledgeChunk[];
  providers_used?: string[];
  [key: string]: unknown;
}

/** Final payload for composed multi-workflow runs (/v2/query with multi-intent). */
export interface FinalComposedPayload {
  query: string;
  sections: RuntimeSection[];
  [key: string]: unknown;
}

export type FinalResultPayload = FinalSingleWorkflowPayload | FinalComposedPayload;

/** Partial payload from a workflow's intermediate `partial_stream` node. */
export interface PartialResultPayload {
  results?: Array<PlaceItem | EventItem>;
  status?: string;
  [key: string]: unknown;
}

// ── Discriminated union of every event that crosses the wire ───────────────

export interface PartialResultEvent {
  event: "partial_result";
  data: PartialResultPayload;
}

export interface FinalResultEvent {
  event: "final_result";
  data: FinalResultPayload;
}

export interface StreamHeartbeatEvent {
  event: "stream_heartbeat";
  data: { idle_s?: number };
}

export interface ErrorEvent {
  event: "error";
  data: { message: string };
}

export type RuntimeEvent =
  | PartialResultEvent
  | FinalResultEvent
  | StreamHeartbeatEvent
  | ErrorEvent;

// ── Parse guards ────────────────────────────────────────────────────────────

const ALLOWED_EVENTS = new Set<RuntimeEvent["event"]>([
  "partial_result",
  "final_result",
  "stream_heartbeat",
  "error",
]);

/**
 * Validate that an arbitrary parsed JSON value is a RuntimeEvent.
 * Returns the typed event on success, or null on shape mismatch.
 *
 * Unknown event types (anything not in ALLOWED_EVENTS) are rejected — this
 * is what enforces the invisible-orchestration contract on the client side.
 * If the backend ever leaks an internal event, this returns null and the
 * caller's `onMalformed` hook fires.
 */
export function parseRuntimeEvent(raw: unknown): RuntimeEvent | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  if (typeof obj.event !== "string") return null;
  if (!ALLOWED_EVENTS.has(obj.event as RuntimeEvent["event"])) return null;
  if (!("data" in obj)) return null;
  return obj as unknown as RuntimeEvent;
}

/** Type-narrow helper for switch statements. */
export function isFinalResult(ev: RuntimeEvent): ev is FinalResultEvent {
  return ev.event === "final_result";
}

export function isPartialResult(ev: RuntimeEvent): ev is PartialResultEvent {
  return ev.event === "partial_result";
}

export function isErrorEvent(ev: RuntimeEvent): ev is ErrorEvent {
  return ev.event === "error";
}

export function isComposedFinal(
  payload: FinalResultPayload
): payload is FinalComposedPayload {
  return Array.isArray((payload as FinalComposedPayload).sections);
}
