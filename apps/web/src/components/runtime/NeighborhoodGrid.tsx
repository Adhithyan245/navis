"use client";
/**
 * NeighborhoodGrid — renders dynamic neighborhood_match candidates (canonical
 * Locations) as a card grid. Presentation only.
 */
import { NeighborhoodCard } from "./NeighborhoodCard";
import type { Location } from "@/lib/runtime/location";

export function NeighborhoodGrid({ items }: { items: Location[] }) {
  if (items.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
        No neighborhood matches for your city yet.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((loc) => (
        <NeighborhoodCard key={loc.id} location={loc} />
      ))}
    </div>
  );
}
