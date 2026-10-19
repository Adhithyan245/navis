/**
 * localStorage seam for checklist progress.
 *
 * Same SSR-safe + memoization pattern as profile/storage.ts and
 * saved/storage.ts. `readChecklist` caches against the raw storage
 * string so `useSyncExternalStore` consumers get a stable reference
 * across renders.
 */
import { scopedKey } from "@/lib/account/scope";
import type { ChecklistItemState, ChecklistState } from "./schema";
import { EMPTY_CHECKLIST } from "./schema";

const CHECKLIST_KEY = "navis_checklist_v1";

function safeLocalStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

// ── readChecklist cache ────────────────────────────────────────────────────
let _checklistRaw: string | null | undefined = undefined;
let _checklistSnapshot: ChecklistState = EMPTY_CHECKLIST;

export function readChecklist(): ChecklistState {
  const ls = safeLocalStorage();
  if (!ls) return EMPTY_CHECKLIST;
  let raw: string | null;
  try {
    raw = ls.getItem(scopedKey(CHECKLIST_KEY));
  } catch {
    return EMPTY_CHECKLIST;
  }
  if (raw === _checklistRaw) return _checklistSnapshot;
  _checklistRaw = raw;
  _checklistSnapshot = raw ? parseChecklist(raw) : EMPTY_CHECKLIST;
  return _checklistSnapshot;
}

function parseChecklist(raw: string): ChecklistState {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return EMPTY_CHECKLIST;
    const rawItems = (parsed as { items?: unknown }).items;
    if (!rawItems || typeof rawItems !== "object") return EMPTY_CHECKLIST;
    const items: Record<string, ChecklistItemState> = {};
    for (const [key, val] of Object.entries(rawItems as Record<string, unknown>)) {
      if (isChecklistItemState(val)) {
        items[key] = val;
      }
    }
    return { items };
  } catch {
    return EMPTY_CHECKLIST;
  }
}

function isChecklistItemState(x: unknown): x is ChecklistItemState {
  if (!x || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  return (
    typeof o.id === "string" &&
    (o.status === "todo" ||
      o.status === "in_progress" ||
      o.status === "done" ||
      o.status === "skipped") &&
    typeof o.updatedAt === "number" &&
    (typeof o.notes === "string" || o.notes === undefined)
  );
}

export function writeChecklist(state: ChecklistState): void {
  const ls = safeLocalStorage();
  if (!ls) return;
  try {
    ls.setItem(scopedKey(CHECKLIST_KEY), JSON.stringify(state));
  } catch {
    /* quota or disabled — ignore */
  }
}

export function clearChecklist(): void {
  const ls = safeLocalStorage();
  if (!ls) return;
  try {
    ls.removeItem(scopedKey(CHECKLIST_KEY));
  } catch {
    /* ignore */
  }
}
