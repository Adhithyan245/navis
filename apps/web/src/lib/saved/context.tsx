"use client";
/**
 * SavedItemsContext — single source of truth for the persisted saved-items
 * collection. Foundation only for Phase 1: providers + storage + hook are
 * established here, but no UI components consume them yet.
 *
 * Uses `useSyncExternalStore` for SSR-safe + concurrent-rendering-safe
 * subscription to the localStorage-backed snapshot (memoized in storage.ts).
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import {
  clearSavedItems as storageClear,
  readSavedItems,
  writeSavedItems,
} from "./storage";
import {
  EMPTY_SAVED,
  type SavedEvent,
  type SavedItem,
  type SavedItemKind,
  type SavedItemsState,
} from "./schema";

export interface SavedItemsContextValue {
  ready: boolean;
  state: SavedItemsState;
  saveItem: (item: SavedItem) => void;
  removeItem: (kind: SavedItemKind, id: string) => void;
  isSaved: (kind: SavedItemKind, id: string) => boolean;
  /** Mark an event signed up (saving it if needed) or not; it stays saved either way. */
  setEventSignedUp: (event: SavedEvent, signedUp: boolean) => void;
  clearAll: () => void;
}

const STORAGE_EVENT = "navis:saved-changed";

const SavedItemsContext = createContext<SavedItemsContextValue | null>(null);

function subscribe(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(STORAGE_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(STORAGE_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

function dispatch(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(STORAGE_EVENT));
  }
}

const SSR_STATE: SavedItemsState = EMPTY_SAVED;
const SSR_READY = false;
const CLIENT_READY = true;

export function SavedItemsProvider({ children }: { children: ReactNode }) {
  const state = useSyncExternalStore<SavedItemsState>(
    subscribe,
    readSavedItems,
    () => SSR_STATE
  );
  const ready = useSyncExternalStore<boolean>(
    subscribe,
    () => CLIENT_READY,
    () => SSR_READY
  );

  const saveItem = useCallback((item: SavedItem) => {
    const current = readSavedItems();
    let next: SavedItemsState = current;
    if (item.kind === "place") {
      if (current.savedPlaces.some((p) => p.id === item.id)) return;
      next = { ...current, savedPlaces: [...current.savedPlaces, item] };
    } else if (item.kind === "event") {
      if (current.savedEvents.some((e) => e.id === item.id)) return;
      next = { ...current, savedEvents: [...current.savedEvents, item] };
    } else if (item.kind === "neighborhood") {
      if (current.savedNeighborhoods.some((n) => n.id === item.id)) return;
      next = { ...current, savedNeighborhoods: [...current.savedNeighborhoods, item] };
    } else if (item.kind === "location") {
      if (current.savedLocations.some((l) => l.id === item.id)) return;
      next = { ...current, savedLocations: [...current.savedLocations, item] };
    }
    writeSavedItems(next);
    dispatch();
  }, []);

  const removeItem = useCallback((kind: SavedItemKind, id: string) => {
    const current = readSavedItems();
    let next: SavedItemsState = current;
    if (kind === "place") {
      next = { ...current, savedPlaces: current.savedPlaces.filter((p) => p.id !== id) };
    } else if (kind === "event") {
      next = { ...current, savedEvents: current.savedEvents.filter((e) => e.id !== id) };
    } else if (kind === "neighborhood") {
      next = {
        ...current,
        savedNeighborhoods: current.savedNeighborhoods.filter((n) => n.id !== id),
      };
    } else if (kind === "location") {
      next = {
        ...current,
        savedLocations: current.savedLocations.filter((l) => l.id !== id),
      };
    }
    writeSavedItems(next);
    dispatch();
  }, []);

  const isSaved = useCallback(
    (kind: SavedItemKind, id: string): boolean => {
      if (kind === "place") return state.savedPlaces.some((p) => p.id === id);
      if (kind === "event") return state.savedEvents.some((e) => e.id === id);
      if (kind === "neighborhood")
        return state.savedNeighborhoods.some((n) => n.id === id);
      if (kind === "location")
        return state.savedLocations.some((l) => l.id === id);
      return false;
    },
    [state]
  );

  const setEventSignedUp = useCallback((event: SavedEvent, signedUp: boolean) => {
    const current = readSavedItems();
    const existing = current.savedEvents.find((e) => e.id === event.id);
    const updated: SavedEvent = {
      ...(existing ?? {}),
      ...event,
      savedAt: existing?.savedAt || Date.now(),
      signedUp,
      signedUpAt: signedUp ? Date.now() : undefined,
    };
    const savedEvents = existing
      ? current.savedEvents.map((e) => (e.id === event.id ? updated : e))
      : [...current.savedEvents, updated];
    writeSavedItems({ ...current, savedEvents });
    dispatch();
  }, []);

  const clearAll = useCallback(() => {
    storageClear();
    dispatch();
  }, []);

  const value = useMemo<SavedItemsContextValue>(
    () => ({ ready, state, saveItem, removeItem, isSaved, setEventSignedUp, clearAll }),
    [ready, state, saveItem, removeItem, isSaved, setEventSignedUp, clearAll]
  );

  return <SavedItemsContext.Provider value={value}>{children}</SavedItemsContext.Provider>;
}

export function useSavedItemsContext(): SavedItemsContextValue {
  const ctx = useContext(SavedItemsContext);
  if (!ctx) {
    throw new Error(
      "useSavedItemsContext must be used within <SavedItemsProvider>."
    );
  }
  return ctx;
}
