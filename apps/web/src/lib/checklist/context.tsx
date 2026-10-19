"use client";
/**
 * ChecklistContext — single source of truth for the persisted checklist
 * progress overlay. Mirrors the SavedItemsContext architecture exactly:
 * `useSyncExternalStore`-backed reads, SSR-safe snapshots, custom-event
 * dispatch within the tab + native `storage` event across tabs.
 *
 * Phase 2 foundation only — no UI components consume this yet.
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
  clearChecklist as storageClear,
  readChecklist,
  writeChecklist,
} from "./storage";
import {
  EMPTY_CHECKLIST,
  type ChecklistState,
  type ChecklistStatus,
} from "./schema";

export interface ChecklistContextValue {
  ready: boolean;
  checklist: ChecklistState;
  setStatus: (id: string, status: ChecklistStatus) => void;
  setNotes: (id: string, notes: string) => void;
  resetItem: (id: string) => void;
  clearAll: () => void;
}

const STORAGE_EVENT = "navis:checklist-changed";

const ChecklistContext = createContext<ChecklistContextValue | null>(null);

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

function noopSubscribe(): () => void {
  return () => {};
}

const SSR_STATE: ChecklistState = EMPTY_CHECKLIST;
const SSR_READY = false;
const CLIENT_READY = true;

export function ChecklistProvider({ children }: { children: ReactNode }) {
  const checklist = useSyncExternalStore<ChecklistState>(
    subscribe,
    readChecklist,
    () => SSR_STATE
  );
  const ready = useSyncExternalStore<boolean>(
    noopSubscribe,
    () => CLIENT_READY,
    () => SSR_READY
  );

  const setStatus = useCallback((id: string, status: ChecklistStatus) => {
    const current = readChecklist();
    const existing = current.items[id];
    const next: ChecklistState = {
      items: {
        ...current.items,
        [id]: {
          id,
          status,
          updatedAt: Date.now(),
          notes: existing?.notes,
        },
      },
    };
    writeChecklist(next);
    dispatch();
  }, []);

  const setNotes = useCallback((id: string, notes: string) => {
    const current = readChecklist();
    const existing = current.items[id];
    const next: ChecklistState = {
      items: {
        ...current.items,
        [id]: {
          id,
          status: existing?.status ?? "todo",
          updatedAt: Date.now(),
          notes,
        },
      },
    };
    writeChecklist(next);
    dispatch();
  }, []);

  const resetItem = useCallback((id: string) => {
    const current = readChecklist();
    if (!(id in current.items)) return;
    const items = { ...current.items };
    delete items[id];
    writeChecklist({ items });
    dispatch();
  }, []);

  const clearAll = useCallback(() => {
    storageClear();
    dispatch();
  }, []);

  const value = useMemo<ChecklistContextValue>(
    () => ({ ready, checklist, setStatus, setNotes, resetItem, clearAll }),
    [ready, checklist, setStatus, setNotes, resetItem, clearAll]
  );

  return <ChecklistContext.Provider value={value}>{children}</ChecklistContext.Provider>;
}

export function useChecklistContext(): ChecklistContextValue {
  const ctx = useContext(ChecklistContext);
  if (!ctx) {
    throw new Error(
      "useChecklistContext must be used within <ChecklistProvider>."
    );
  }
  return ctx;
}
