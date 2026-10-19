/**
 * ChecklistState — per-item progress overlay for the corpus-defined
 * essentials / relocation checklist.
 *
 * The corpus owns item TEMPLATES (each markdown file in
 * knowledge/checklist/ has a stable `frontmatter.id`). This state owns
 * only the user's PROGRESS on each item, keyed by that same id. The two
 * stay decoupled — when corpus items are renamed or removed, orphaned
 * progress entries sit harmlessly in storage until cleared.
 *
 * Persisted to localStorage under `navis_checklist_v1`.
 */

export type ChecklistStatus = "todo" | "in_progress" | "done" | "skipped";

export interface ChecklistItemState {
  id: string;
  status: ChecklistStatus;
  updatedAt: number;          // Unix milliseconds
  notes?: string;
}

export interface ChecklistState {
  items: Record<string, ChecklistItemState>;
}

export const EMPTY_CHECKLIST: ChecklistState = {
  items: {},
};
