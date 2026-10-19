"use client";
/**
 * /explore — dynamic city exploration.
 *
 * Runs the `city_explorer` workflow (auto-injecting the persisted profile)
 * and renders discovered places as an ExplorerGrid. An optional category
 * filter re-runs the workflow with `{ category }` merged into user_context.
 */
import { useEffect, useRef, useState } from "react";
import { Compass } from "lucide-react";

import { ExplorerGrid } from "@/components/runtime/ExplorerGrid";
import { Button } from "@/components/ui/button";
import { useNavisWorkflow } from "@/hooks/useNavisWorkflow";
import { isLocation, type Location } from "@/lib/runtime/location";
import { useProfileContext } from "@/lib/profile/context";
import { cn } from "@/lib/utils";

const CATEGORIES: { label: string; value: string | null }[] = [
  { label: "All", value: null },
  { label: "Neighborhoods", value: "neighborhoods" },
  { label: "Landmarks", value: "landmarks" },
  { label: "Parks", value: "parks" },
  { label: "Shopping", value: "shopping" },
  { label: "Business", value: "business" },
  { label: "Transit", value: "transit" },
];

function toItems(result: Record<string, unknown> | null): Location[] {
  if (!result) return [];
  const results = result.results;
  if (!Array.isArray(results)) return [];
  return results.filter(isLocation);
}

export default function ExplorePage() {
  const { ready, profile, restoreOnboarding } = useProfileContext();
  const { run, loading, error, result } = useNavisWorkflow("city_explorer");
  const [category, setCategory] = useState<string | null>(null);
  const ranForRef = useRef<string | null>(null);

  useEffect(() => {
    if (!ready || !profile) return;
    const key = `${profile.city}|${category ?? ""}`;
    if (ranForRef.current === key) return;
    ranForRef.current = key;
    const ctx = category ? { category } : {};
    void run(`Explore ${profile.city || "my city"}`, ctx);
  }, [ready, profile, category, run]);

  if (!ready) {
    return (
      <div className="py-12 text-sm text-zinc-500 dark:text-zinc-400">
        Loading…
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center justify-center gap-6 py-16 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-indigo-50 dark:bg-indigo-950/40">
          <Compass className="size-6 text-indigo-500" />
        </div>
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            Set up your profile first
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Tell Navis which city you&apos;re in and we&apos;ll surface places,
            districts, and landmarks to explore.
          </p>
        </div>
        <Button onClick={restoreOnboarding}>Set up profile</Button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 py-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
          Explore{profile.city ? ` ${profile.city}` : ""}
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Districts, landmarks, and areas around your city.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((c) => (
          <button
            key={c.label}
            type="button"
            onClick={() => setCategory(c.value)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
              category === c.value
                ? "border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-500/40 dark:bg-indigo-950/40 dark:text-indigo-300"
                : "border-zinc-200 bg-white text-zinc-700 hover:border-indigo-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="py-12 text-center text-sm text-zinc-500 dark:text-zinc-400">
          Exploring…
        </div>
      )}

      {!loading && error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/30 dark:text-rose-300">
          {error}
        </div>
      )}

      {!loading && !error && result && (
        <ExplorerGrid items={toItems(result as Record<string, unknown>)} />
      )}
    </div>
  );
}
