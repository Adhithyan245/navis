"use client";
/**
 * ChecklistCard — renders one essentials item (corpus template + persisted
 * progress) and lets the user move it through todo → in_progress → done →
 * skipped via ChecklistContext.
 *
 * The corpus owns the template fields (id, title, urgency); ChecklistContext
 * owns the per-id status. This component just joins the two.
 */
import { ExternalLink } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { useChecklistContext } from "@/lib/checklist/context";
import type { ChecklistStatus } from "@/lib/checklist/schema";
import { cn } from "@/lib/utils";

export interface ChecklistItem {
  id: string;
  title: string;
  urgency: string;
  /** Short how-to (the chunk body), when the corpus has one. */
  detail?: string | null;
  /** Official site for this step. */
  link?: string | null;
  /** True for items compiled by AI for places without a hand-written guide. */
  generated?: boolean;
}

const STATUS_OPTIONS: { value: ChecklistStatus; label: string }[] = [
  { value: "todo", label: "To do" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
  { value: "skipped", label: "Skipped" },
];

const URGENCY_STYLES: Record<string, string> = {
  high: "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
  medium: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
  low: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
};

export function ChecklistCard({ item }: { item: ChecklistItem }) {
  const { checklist, setStatus } = useChecklistContext();
  const status: ChecklistStatus = checklist.items[item.id]?.status ?? "todo";

  return (
    <Card className="h-full">
      <CardContent className="flex h-full flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <h4
            className={cn(
              "text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100",
              status === "done" && "line-through text-zinc-400 dark:text-zinc-500",
              status === "skipped" && "text-zinc-400 dark:text-zinc-500"
            )}
          >
            {item.title}
          </h4>
          <span
            className={cn(
              "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium",
              URGENCY_STYLES[item.urgency.toLowerCase()] ??
                "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
            )}
          >
            {item.urgency}
          </span>
        </div>

        {item.detail && (
          <p
            className={cn(
              "text-[13px] leading-relaxed text-zinc-600 dark:text-zinc-400",
              (status === "done" || status === "skipped") && "line-clamp-2"
            )}
          >
            {item.detail}
          </p>
        )}
        {item.link && (
          <a
            href={item.link}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex w-fit items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
          >
            Official site <ExternalLink className="size-3" />
          </a>
        )}

        <div className="mt-auto flex flex-wrap gap-1.5">
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setStatus(item.id, opt.value)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                status === opt.value
                  ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-950/40 dark:text-indigo-300"
                  : "border-zinc-200 bg-white text-zinc-600 hover:border-indigo-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400"
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
