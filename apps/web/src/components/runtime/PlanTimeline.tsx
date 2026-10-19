"use client";
/**
 * PlanTimeline — renders relocation plan items as a vertical, phase-ordered
 * timeline. Items are grouped by their corpus `stage` (pre_arrival → week_1 →
 * month_1 → month_3 → universal). Per-item status overlays from
 * ChecklistContext when the item id has tracked progress.
 */
import { useChecklistContext } from "@/lib/checklist/context";
import type { ChecklistStatus } from "@/lib/checklist/schema";
import { cn } from "@/lib/utils";

export interface PlanItem {
  id: string;
  title: string;
  urgency: string;
  stage: string;
}

const PHASE_ORDER = ["pre_arrival", "week_1", "month_1", "month_3"] as const;

const PHASE_LABELS: Record<string, string> = {
  pre_arrival: "Before you move",
  week_1: "First week",
  month_1: "First month",
  month_3: "First three months",
  universal: "Anytime",
};

const STATUS_LABELS: Record<ChecklistStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  done: "Done",
  skipped: "Skipped",
};

const STATUS_STYLES: Record<ChecklistStatus, string> = {
  todo: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  in_progress: "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300",
  done: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
  skipped: "bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-500",
};

const URGENCY_STYLES: Record<string, string> = {
  high: "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
  medium: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
  low: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
};

function phaseKey(stage: string): string {
  const s = stage.toLowerCase();
  return (PHASE_ORDER as readonly string[]).includes(s) ? s : "universal";
}

export function PlanTimeline({ items }: { items: PlanItem[] }) {
  const { checklist } = useChecklistContext();

  if (items.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
        No plan steps found for your profile yet.
      </p>
    );
  }

  const order = [...PHASE_ORDER, "universal"];
  const phases = order
    .map((key) => ({
      key,
      label: PHASE_LABELS[key],
      items: items.filter((it) => phaseKey(it.stage) === key),
    }))
    .filter((p) => p.items.length > 0);

  return (
    <ol className="flex flex-col gap-8 border-l border-zinc-200 pl-6 dark:border-zinc-800">
      {phases.map((phase) => (
        <li key={phase.key} className="relative">
          <span className="absolute -left-[31px] top-1 size-3 rounded-full border-2 border-indigo-400 bg-white dark:bg-zinc-950" />
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {phase.label}
          </h3>
          <ul className="mt-3 flex flex-col gap-2">
            {phase.items.map((item) => {
              const status = checklist.items[item.id]?.status ?? null;
              return (
                <li
                  key={item.id}
                  className="flex items-start justify-between gap-3 rounded-lg border border-zinc-200 bg-white px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900"
                >
                  <span
                    className={cn(
                      "text-sm text-zinc-800 dark:text-zinc-200",
                      status === "done" && "line-through text-zinc-400 dark:text-zinc-500",
                      status === "skipped" && "text-zinc-400 dark:text-zinc-500"
                    )}
                  >
                    {item.title}
                  </span>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[10px] font-medium",
                        URGENCY_STYLES[item.urgency.toLowerCase()] ??
                          "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
                      )}
                    >
                      {item.urgency}
                    </span>
                    {status && (
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-medium",
                          STATUS_STYLES[status]
                        )}
                      >
                        {STATUS_LABELS[status]}
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ol>
  );
}
