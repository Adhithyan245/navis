/**
 * localStorage seam for saved items (places / events / neighborhoods).
 *
 * Same SSR-safe + memoization pattern as profile/storage.ts. `readSavedItems`
 * caches against the raw storage string so `useSyncExternalStore` consumers
 * get a stable reference across renders.
 */
import { scopedKey } from "@/lib/account/scope";
import type {
  SavedEvent,
  SavedItemsState,
  SavedLocation,
  SavedNeighborhood,
  SavedPlace,
} from "./schema";
import { EMPTY_SAVED } from "./schema";

const SAVED_KEY = "navis_saved_items_v1";

function safeLocalStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

// ── readSavedItems cache ──────────────────────────────────────────────────
let _savedRaw: string | null | undefined = undefined;
let _savedSnapshot: SavedItemsState = EMPTY_SAVED;

export function readSavedItems(): SavedItemsState {
  const ls = safeLocalStorage();
  if (!ls) return EMPTY_SAVED;
  let raw: string | null;
  try {
    raw = ls.getItem(scopedKey(SAVED_KEY));
  } catch {
    return EMPTY_SAVED;
  }
  if (raw === _savedRaw) return _savedSnapshot;
  _savedRaw = raw;
  _savedSnapshot = raw ? parseSavedItems(raw) : EMPTY_SAVED;
  return _savedSnapshot;
}

function parseSavedItems(raw: string): SavedItemsState {
  try {
    const parsed = JSON.parse(raw);
    return {
      savedPlaces: Array.isArray(parsed?.savedPlaces)
        ? parsed.savedPlaces.filter(isSavedPlace)
        : [],
      savedEvents: Array.isArray(parsed?.savedEvents)
        ? parsed.savedEvents.filter(isSavedEvent)
        : [],
      savedNeighborhoods: Array.isArray(parsed?.savedNeighborhoods)
        ? parsed.savedNeighborhoods.filter(isSavedNeighborhood)
        : [],
      savedLocations: Array.isArray(parsed?.savedLocations)
        ? parsed.savedLocations.filter(isSavedLocation)
        : [],
    };
  } catch {
    return EMPTY_SAVED;
  }
}

export function writeSavedItems(state: SavedItemsState): void {
  const ls = safeLocalStorage();
  if (!ls) return;
  try {
    ls.setItem(scopedKey(SAVED_KEY), JSON.stringify(state));
  } catch {
    /* quota or disabled — ignore */
  }
}

export function clearSavedItems(): void {
  const ls = safeLocalStorage();
  if (!ls) return;
  try {
    ls.removeItem(scopedKey(SAVED_KEY));
  } catch {
    /* ignore */
  }
}

function isSavedPlace(x: unknown): x is SavedPlace {
  if (!x || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  return (
    o.kind === "place" &&
    typeof o.id === "string" &&
    typeof o.title === "string" &&
    typeof o.savedAt === "number"
  );
}

function isSavedEvent(x: unknown): x is SavedEvent {
  if (!x || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  return (
    o.kind === "event" &&
    typeof o.id === "string" &&
    typeof o.title === "string" &&
    typeof o.savedAt === "number"
  );
}

function isSavedNeighborhood(x: unknown): x is SavedNeighborhood {
  if (!x || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  return (
    o.kind === "neighborhood" &&
    typeof o.id === "string" &&
    typeof o.title === "string" &&
    typeof o.city === "string" &&
    typeof o.savedAt === "number"
  );
}

function isSavedLocation(x: unknown): x is SavedLocation {
  if (!x || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  return (
    o.kind === "location" &&
    typeof o.id === "string" &&
    typeof o.label === "string" &&
    typeof o.type === "string" &&
    typeof o.savedAt === "number"
  );
}
