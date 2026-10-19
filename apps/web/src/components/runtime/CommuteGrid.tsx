"use client";
/**
 * CommuteGrid — renders commute_analysis estimates (one card per mode) as a
 * grid. Presentation only.
 */
import { CommuteCard } from "./CommuteCard";
import type { Commute } from "@/lib/runtime/commute";

export function CommuteGrid({ items }: { items: Commute[] }) {
  if (items.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
        No commute estimates available for this route yet.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {items.map((c) => (
        <CommuteCard key={`${c.mode}-${c.provider}`} commute={c} />
      ))}
    </div>
  );
}
