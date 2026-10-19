"use client";
/**
 * /match — neighborhood candidates matched to the user's profile.
 *
 * Runs the `neighborhood_match` workflow (auto-injecting the persisted
 * profile) and renders the returned corpus chunks as a NeighborhoodGrid.
 */
import { useEffect, useRef } from "react";
import { Compass } from "lucide-react";

import { NeighborhoodGrid } from "@/components/runtime/NeighborhoodGrid";
import { Button } from "@/components/ui/button";
import { useNavisWorkflow } from "@/hooks/useNavisWorkflow";
import { isLocation, type Location } from "@/lib/runtime/location";
import { useProfileContext } from "@/lib/profile/context";

function toItems(result: Record<string, unknown> | null): Location[] {
  if (!result) return [];
  const candidates = result.candidates;
  if (!Array.isArray(candidates)) return [];
  return candidates.filter(isLocation);
}

export default function MatchPage() {
  const { ready, profile, restoreOnboarding } = useProfileContext();
  const { run, loading, error, result } = useNavisWorkflow("neighborhood_match");
  const ranForRef = useRef<string | null>(null);

  useEffect(() => {
    if (!ready || !profile) return;
    const key = `${profile.city}|${profile.homeArea}|${profile.household}|${profile.budgetBand}|${profile.workStyle}`;
    if (ranForRef.current === key) return;
    ranForRef.current = key;
    void run(`Neighborhoods in ${profile.city || "my new city"} for me`);
  }, [ready, profile, run]);

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
            Tell Navis about your move and we&apos;ll match neighborhoods to your
            household, budget, and work style.
          </p>
        </div>
        <Button onClick={restoreOnboarding}>Set up profile</Button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 py-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
          Neighborhood matches
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Areas{profile.city ? ` in ${profile.city}` : ""} that fit your profile.
          Save the ones you like.
        </p>
      </header>

      {loading && (
        <div className="py-12 text-center text-sm text-zinc-500 dark:text-zinc-400">
          Finding your matches…
        </div>
      )}

      {!loading && error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/30 dark:text-rose-300">
          {error}
        </div>
      )}

      {!loading && !error && result && (
        <NeighborhoodGrid items={toItems(result as Record<string, unknown>)} />
      )}
    </div>
  );
}
