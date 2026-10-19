"use client";
/**
 * ChecklistGrid — groups essentials items by urgency (high → medium → low →
 * other) and renders a ChecklistCard per item. Progress lives in
 * ChecklistContext; this component is presentation only.
 */
import { ChecklistCard, type ChecklistItem } from "./ChecklistCard";

const URGENCY_ORDER = ["high", "medium", "low"] as const;

const GROUP_LABELS: Record<string, string> = {
  high: "Do first",
  medium: "Soon",
  low: "When you can",
  other: "Other",
};

function groupKey(urgency: string): string {
  const u = urgency.toLowerCase();
  return (URGENCY_ORDER as readonly string[]).includes(u) ? u : "other";
}

export function ChecklistGrid({ items }: { items: ChecklistItem[] }) {
  if (items.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
        No essentials found for your city yet.
      </p>
    );
  }

  const order = [...URGENCY_ORDER, "other"];
  const groups = order
    .map((key) => ({
      key,
      label: GROUP_LABELS[key],
      items: items.filter((it) => groupKey(it.urgency) === key),
    }))
    .filter((g) => g.items.length > 0);

  return (
    <div className="flex flex-col gap-8">
      {groups.map((group) => (
        <section key={group.key} className="flex flex-col gap-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            {group.label}
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {group.items.map((item) => (
              <ChecklistCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
