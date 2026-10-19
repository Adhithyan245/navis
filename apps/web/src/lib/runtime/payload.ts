/**
 * Shape adapters for workflow payloads that aren't plain `results[]`.
 *
 * commute_analysis → `commutes`, neighborhood_match → `candidates`,
 * relocation_plan / essentials_checklist → corpus `chunks`. Shared by the
 * dedicated pages and the home-page ResultStream so a free-text question
 * renders the same cards as its page.
 */
import type { ChecklistItem } from "@/components/runtime/ChecklistCard";
import type { PlanItem } from "@/components/runtime/PlanTimeline";
import { isCommute, type Commute } from "@/lib/runtime/commute";
import { isLocation, type Location } from "@/lib/runtime/location";

type Payload = Record<string, unknown> | null | undefined;

interface ChunkView {
  frontmatter?: Record<string, unknown>;
  body?: unknown;
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}

function frontmatters(result: Payload): Record<string, unknown>[] {
  const chunks = result?.chunks;
  if (!Array.isArray(chunks)) return [];
  const out: Record<string, unknown>[] = [];
  for (const raw of chunks as ChunkView[]) {
    const fm = raw?.frontmatter;
    // Carry the body along as `_body` so item builders can show it.
    if (fm && typeof fm === "object") out.push({ ...fm, _body: raw.body });
  }
  return out;
}

/** First paragraph of a markdown body, flattened to one line. */
function summary(body: unknown): string | null {
  if (typeof body !== "string") return null;
  const first = body.trim().split(/\n\s*\n/)[0] ?? "";
  const text = first.replace(/\s+/g, " ").trim();
  return text ? text.slice(0, 400) : null;
}

/** True when any item was AI-compiled (no hand-written guide for the place). */
export function hasGeneratedItems(result: Payload): boolean {
  return frontmatters(result).some((f) => f.generated === true);
}

export function toCommutes(result: Payload): Commute[] {
  const commutes = result?.commutes;
  return Array.isArray(commutes) ? commutes.filter(isCommute) : [];
}

export function toNeighborhoods(result: Payload): Location[] {
  const candidates = result?.candidates;
  return Array.isArray(candidates) ? candidates.filter(isLocation) : [];
}

export function toChecklistItems(result: Payload): ChecklistItem[] {
  const items: ChecklistItem[] = [];
  for (const f of frontmatters(result)) {
    const id = str(f.id);
    const title = str(f.title);
    if (!id || !title) continue;
    items.push({
      id,
      title,
      urgency: str(f.urgency) ?? "medium",
      detail: summary(f._body),
      link: str(f.external_link),
      generated: f.generated === true,
    });
  }
  return items;
}

export function toPlanItems(result: Payload): PlanItem[] {
  const items: PlanItem[] = [];
  for (const f of frontmatters(result)) {
    const id = str(f.id);
    const title = str(f.title);
    if (!id || !title) continue;
    items.push({
      id,
      title,
      urgency: str(f.urgency) ?? "medium",
      stage: str(f.stage) ?? "universal",
    });
  }
  return items;
}

/** Plan chunks carry a `stage`; checklist chunks don't. */
export function chunksArePlan(result: Payload): boolean {
  return frontmatters(result).some((f) => str(f.stage) !== null);
}
