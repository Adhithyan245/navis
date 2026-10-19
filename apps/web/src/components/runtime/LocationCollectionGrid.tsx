"use client";
/**
 * LocationCollectionGrid — renders saved canonical locations as a card grid.
 * Presentation only; filtering and sorting are owned by the caller (the
 * /locations page), so future ordering logic needs no changes here.
 */
import { LocationCollectionCard } from "./LocationCollectionCard";
import type { SavedLocation } from "@/lib/saved/schema";

export function LocationCollectionGrid({ items }: { items: SavedLocation[] }) {
  if (items.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400">
        No saved locations match this filter.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((item) => (
        <LocationCollectionCard key={item.id} item={item} />
      ))}
    </div>
  );
}
