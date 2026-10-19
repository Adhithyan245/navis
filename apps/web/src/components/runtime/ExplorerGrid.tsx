"use client";
/**
 * ExplorerGrid — renders city_explorer results (canonical Locations) as a
 * card grid. Presentation only; ordering is the caller's responsibility so a
 * future ranking layer can sort before passing items in.
 */
import { ExplorerCard } from "./ExplorerCard";
import type { Location } from "@/lib/runtime/location";

export function ExplorerGrid({ items }: { items: Location[] }) {
  if (items.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
        Nothing to explore here yet.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((loc) => (
        <ExplorerCard key={loc.id} location={loc} />
      ))}
    </div>
  );
}
