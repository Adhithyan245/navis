"use client";
/**
 * /locations — unified saved-location collection.
 *
 * Reads canonical saved locations from SavedItemsContext (localStorage). Saved
 * from NeighborhoodCard and ExplorerCard (and any future location workflow).
 * Supports filtering by bucket and sorting. No backend dependency.
 */
import { useMemo, useState } from "react";
import { MapPinned } from "lucide-react";

import { LocationCollectionGrid } from "@/components/runtime/LocationCollectionGrid";
import { useSavedItemsContext } from "@/lib/saved/context";
import type { SavedLocation } from "@/lib/saved/schema";
import { cn } from "@/lib/utils";

type Bucket =
  | "Neighborhood"
  | "District"
  | "Landmark"
  | "Park"
  | "Transit"
  | "Shopping"
  | "Other";

const FILTERS: (Bucket | "All")[] = [
  "All",
  "Neighborhood",
  "District",
  "Landmark",
  "Park",
  "Transit",
  "Shopping",
  "Other",
];

const BUCKET_ORDER: Bucket[] = [
  "Neighborhood",
  "District",
  "Landmark",
  "Park",
  "Transit",
  "Shopping",
  "Other",
];

type SortKey = "recent" | "alpha" | "type";
const SORTS: { label: string; value: SortKey }[] = [
  { label: "Recently saved", value: "recent" },
  { label: "Alphabetical", value: "alpha" },
  { label: "Type", value: "type" },
];

function bucketOf(loc: SavedLocation): Bucket {
  const tags = (loc.tags ?? []).map((t) => t.toLowerCase());
  const has = (...keys: string[]) =>
    tags.some((tag) => keys.some((k) => tag.includes(k)));

  if (loc.type === "suburb" || loc.type === "neighborhood") return "Neighborhood";
  if (loc.type === "district") return "District";
  if (has("park", "garden", "national park")) return "Park";
  if (has("transit", "public transport", "station", "airport", "subway", "bus", "railway"))
    return "Transit";
  if (has("shopping", "mall", "marketplace", "market")) return "Shopping";
  if (loc.type === "landmark") return "Landmark";
  return "Other";
}

export default function LocationsPage() {
  const { ready, state } = useSavedItemsContext();
  const [filter, setFilter] = useState<Bucket | "All">("All");
  const [sort, setSort] = useState<SortKey>("recent");

  const visible = useMemo(() => {
    const items = state.savedLocations;
    const filtered =
      filter === "All" ? items : items.filter((l) => bucketOf(l) === filter);
    const sorted = [...filtered];
    if (sort === "recent") {
      sorted.sort((a, b) => b.savedAt - a.savedAt);
    } else if (sort === "alpha") {
      sorted.sort((a, b) => a.label.localeCompare(b.label));
    } else {
      sorted.sort((a, b) => {
        const ai = BUCKET_ORDER.indexOf(bucketOf(a));
        const bi = BUCKET_ORDER.indexOf(bucketOf(b));
        return ai !== bi ? ai - bi : a.label.localeCompare(b.label);
      });
    }
    return sorted;
  }, [state.savedLocations, filter, sort]);

  if (!ready) {
    return (
      <div className="py-12 text-sm text-zinc-500 dark:text-zinc-400">
        Loading…
      </div>
    );
  }

  if (state.savedLocations.length === 0) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center justify-center gap-6 py-16 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-indigo-50 dark:bg-indigo-950/40">
          <MapPinned className="size-6 text-indigo-500" />
        </div>
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            No saved locations yet
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Save neighborhoods and places from Match and Explore, and they&apos;ll
            collect here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 py-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
          Saved locations
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Your collection across matches and exploration. Saved to your account.
        </p>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                filter === f
                  ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-950/40 dark:text-indigo-300"
                  : "border-zinc-200 bg-white text-zinc-700 hover:border-indigo-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
              )}
            >
              {f}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5">
          {SORTS.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => setSort(s.value)}
              className={cn(
                "rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors",
                sort === s.value
                  ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-950/40 dark:text-indigo-300"
                  : "border-zinc-200 bg-white text-zinc-600 hover:border-indigo-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400"
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <LocationCollectionGrid items={visible} />
    </div>
  );
}
