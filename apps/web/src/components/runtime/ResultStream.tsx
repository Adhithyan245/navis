"use client";
/**
 * ResultStream — progressive rendering of a Navis runtime stream.
 *
 * Decision tree for what to show:
 *   1. If `final` arrived: render the assembled final view (summary + items + context).
 *   2. Else if `partials` has items: render the latest partial as a "refining"
 *      preview so the user sees results before humanization finishes.
 *   3. Else: render the streaming spinner.
 *
 * Composed (multi-workflow) finals carry a `sections[]` array — one section
 * per workflow, labeled by `kind` (never workflow id). Single-workflow finals
 * carry `results[]` directly. Both paths render through the same item view.
 */
import { Loader2, Sparkles } from "lucide-react";

import { ChecklistGrid } from "@/components/runtime/ChecklistGrid";
import { CommuteGrid } from "@/components/runtime/CommuteGrid";
import { EventCard } from "@/components/runtime/EventCard";
import { NeighborhoodGrid } from "@/components/runtime/NeighborhoodGrid";
import { PlaceCard } from "@/components/runtime/PlaceCard";
import { PlanTimeline } from "@/components/runtime/PlanTimeline";
import type {
  EventItem,
  FinalResultPayload,
  PartialResultPayload,
  PlaceItem,
} from "@/lib/runtime/events";
import { isComposedFinal, type RuntimeSection } from "@/lib/runtime/events";
import {
  AgentSectionBody,
  DOMAIN_KINDS,
  SectionLead,
  SectionStatusNote,
} from "@/components/runtime/AgentSections";
import {
  chunksArePlan,
  toChecklistItems,
  toCommutes,
  toNeighborhoods,
  toPlanItems,
} from "@/lib/runtime/payload";

interface ResultStreamProps {
  partials: PartialResultPayload[];
  final: FinalResultPayload | null;
  streaming: boolean;
}

export function ResultStream({ partials, final, streaming }: ResultStreamProps) {
  if (final) {
    return <FinalView payload={final} />;
  }

  // Agent sections stream in one by one as each agent finishes.
  const streamedSections = partials
    .map((p) => (p.section && typeof p.section === "object" ? (p.section as RuntimeSection) : null))
    .filter((s): s is RuntimeSection => s !== null);
  if (streamedSections.length > 0) {
    return (
      <div className="space-y-8">
        {streaming && (
          <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
            <Loader2 className="size-3 animate-spin" />
            <span>More on the way…</span>
          </div>
        )}
        {streamedSections.map((section, idx) => (
          <SectionBlock key={`${section.kind}-${idx}`} section={section} />
        ))}
      </div>
    );
  }

  const latestPartial = partials[partials.length - 1];
  if (latestPartial) {
    return <PartialView partial={latestPartial} streaming={streaming} />;
  }

  if (streaming) {
    return <StreamingPlaceholder />;
  }

  return null;
}

// ── Subviews ────────────────────────────────────────────────────────────────

function FinalView({ payload }: { payload: FinalResultPayload }) {
  if (isComposedFinal(payload)) {
    const lead = typeof payload.summary === "string" ? payload.summary : null;
    return (
      <div className="space-y-8">
        {lead && <AnswerCard text={lead} />}
        {payload.sections.map((section, idx) => (
          <SectionBlock key={`${section.kind}-${idx}`} section={section} />
        ))}
      </div>
    );
  }

  // Single-workflow final
  const summary = typeof payload.summary === "string" ? payload.summary : null;

  return (
    <div className="space-y-6">
      {summary && <AnswerCard text={summary} />}
      <PayloadBody payload={payload as Record<string, unknown>} />
    </div>
  );
}

/**
 * Render a workflow payload by its shape. Only explore/work/connect return
 * `results[]`; commute, neighborhood, plan and checklist answers carry
 * their own fields and previously rendered as "Nothing to show here yet".
 */
function PayloadBody({ payload, limit }: { payload: Record<string, unknown>; limit?: number }) {
  if (Array.isArray(payload.commutes)) {
    const commutes = toCommutes(payload);
    if (commutes.length > 0) return <CommuteGrid items={commutes} />;
    return <EmptyNote text="Couldn't estimate that trip. Try naming both places, like “from Back Bay to Kendall Square”." />;
  }
  if (Array.isArray(payload.candidates)) {
    return <NeighborhoodGrid items={toNeighborhoods(payload)} />;
  }
  if (Array.isArray(payload.chunks)) {
    return chunksArePlan(payload) ? (
      <PlanTimeline items={toPlanItems(payload)} />
    ) : (
      <ChecklistGrid items={toChecklistItems(payload)} />
    );
  }
  const results = Array.isArray(payload.results)
    ? (payload.results as Array<PlaceItem | EventItem>)
    : [];
  return <ItemGrid items={limit ? results.slice(0, limit) : results} />;
}

function EmptyNote({ text }: { text: string }) {
  return (
    <p className="rounded-2xl border border-dashed border-zinc-300/80 px-4 py-8 text-center text-sm text-zinc-500 dark:border-white/10 dark:text-zinc-400">
      {text}
    </p>
  );
}

function PartialView({
  partial,
  streaming,
}: {
  partial: PartialResultPayload;
  streaming: boolean;
}) {
  const results = Array.isArray(partial.results) ? partial.results : [];

  return (
    <div className="space-y-4">
      {streaming && (
        <div className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
          <Loader2 className="size-3 animate-spin" />
          <span>Refining…</span>
        </div>
      )}
      <ItemGrid items={results} />
    </div>
  );
}

function StreamingPlaceholder() {
  return (
    <div role="status" aria-label="Working on it" className="space-y-4">
      <div className="h-20 rounded-2xl bg-gradient-to-r from-zinc-100 via-zinc-200/70 to-zinc-100 bg-[length:200%_100%] animate-shimmer dark:from-zinc-900 dark:via-zinc-800 dark:to-zinc-900" />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-32 rounded-2xl bg-gradient-to-r from-zinc-100 via-zinc-200/70 to-zinc-100 bg-[length:200%_100%] animate-shimmer dark:from-zinc-900 dark:via-zinc-800 dark:to-zinc-900"
          />
        ))}
      </div>
    </div>
  );
}

function AnswerCard({ text }: { text: string }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-indigo-200/60 bg-gradient-to-br from-indigo-50/90 via-white/80 to-fuchsia-50/60 p-5 shadow-soft dark:border-indigo-400/15 dark:from-indigo-500/10 dark:via-zinc-900/60 dark:to-fuchsia-500/5">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold tracking-wide text-indigo-700 uppercase dark:text-indigo-300">
        <Sparkles className="size-3.5" aria-hidden />
        Navis
      </div>
      <p className="whitespace-pre-line text-[15px] leading-relaxed text-zinc-800 dark:text-zinc-200">
        {renderInlineBold(text)}
      </p>
    </div>
  );
}

/** Render `**bold**` spans; everything else stays plain text. */
function renderInlineBold(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={i} className="font-semibold text-zinc-900 dark:text-zinc-50">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    ),
  );
}

// ── Building blocks ─────────────────────────────────────────────────────────

/**
 * One section of a composed / multi-agent answer. Agent sections carry a
 * title, status and positive message; workflow sections carry their own
 * payload (results/summary/...).
 */
export function SectionBlock({
  section,
  limit,
  hideTitle,
}: {
  section: RuntimeSection;
  limit?: number;
  hideTitle?: boolean;
}) {
  const { kind, data } = section;
  const payload =
    data && typeof data === "object" ? (data as FinalResultPayload) : null;
  const summary =
    payload && typeof payload.summary === "string" ? payload.summary : null;
  const nothingToShow = section.status === "empty" || section.status === "unavailable";

  return (
    <section className="space-y-3">
      {!hideTitle && (
        <h3 className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
          {section.title ?? humanizeKind(kind)}
        </h3>
      )}
      <SectionStatusNote section={section} />
      {DOMAIN_KINDS.has(kind) ? (
        <>
          <SectionLead section={section} />
          {section.status !== "unavailable" && <AgentSectionBody section={section} limit={limit} />}
        </>
      ) : (
        <>
          {summary && <AnswerCard text={summary} />}
          {!nothingToShow && <PayloadBody payload={(payload ?? {}) as Record<string, unknown>} limit={limit} />}
        </>
      )}
    </section>
  );
}

function ItemGrid({ items }: { items: Array<PlaceItem | EventItem> }) {
  if (items.length === 0) {
    return <EmptyNote text="Nothing to show here yet." />;
  }
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item, idx) => (
        <ItemView key={`${getItemKey(item, idx)}-${idx}`} item={item} />
      ))}
    </div>
  );
}

function ItemView({ item }: { item: PlaceItem | EventItem }) {
  if (isEventItem(item)) {
    return <EventCard event={item} />;
  }
  return <PlaceCard place={item as PlaceItem} />;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function isEventItem(item: PlaceItem | EventItem): item is EventItem {
  // An item is an event if any of the event-specific shapes are present:
  //   * a `title` (Navis canonical shape, used by the test fixtures)
  //   * a `classifications` array (Ticketmaster)
  //   * an `_embedded.venues` array (Ticketmaster)
  //   * a `dates.start` object (Ticketmaster/Eventbrite)
  const e = item as EventItem;
  if (typeof e.title === "string") return true;
  if (Array.isArray(e.classifications)) return true;
  if (e._embedded && Array.isArray(e._embedded.venues)) return true;
  if (e.dates && typeof e.dates === "object" && "start" in e.dates) return true;
  return false;
}

function getItemKey(item: PlaceItem | EventItem, idx: number): string {
  if (typeof (item as EventItem).id === "string") return (item as EventItem).id as string;
  const props = (item as PlaceItem).properties;
  if (props && typeof props.place_id === "string") return props.place_id;
  if (typeof (item as PlaceItem).name === "string") return (item as PlaceItem).name as string;
  if (typeof (item as EventItem).title === "string") return (item as EventItem).title as string;
  return String(idx);
}

function humanizeKind(kind: string): string {
  // Map known section_kind values to a friendly label. Unknown kinds
  // pass through unchanged so the backend can introduce new categories
  // without a frontend deploy.
  const map: Record<string, string> = {
    explore: "Places to explore",
    work: "Work-friendly spots",
    events: "Events happening near you",
    commute: "Getting there",
    neighborhoods: "Neighborhoods to consider",
    plan: "Your move plan",
    checklist: "Essentials checklist",
  };
  return map[kind] ?? kind.replace(/_/g, " ");
}
