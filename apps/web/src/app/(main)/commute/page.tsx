"use client";
/**
 * /commute — travel-time analysis between an origin and a destination.
 *
 * Seeds origin/destination from the profile (home area / city → office) and
 * lets the user override either via LocationSearch. Runs the commute_analysis
 * workflow and renders one CommuteCard per mode.
 */
import { useEffect, useRef, useState } from "react";
import { Navigation } from "lucide-react";

import { CommuteGrid } from "@/components/runtime/CommuteGrid";
import { LocationSearch } from "@/components/runtime/LocationSearch";
import { Button } from "@/components/ui/button";
import { useNavisWorkflow } from "@/hooks/useNavisWorkflow";
import { isCommute, type Commute } from "@/lib/runtime/commute";
import type { Location } from "@/lib/runtime/location";
import { useProfileContext } from "@/lib/profile/context";

function toCommutes(result: Record<string, unknown> | null): Commute[] {
  if (!result) return [];
  const commutes = result.commutes;
  if (!Array.isArray(commutes)) return [];
  return commutes.filter(isCommute);
}

export default function CommutePage() {
  const { ready, profile, restoreOnboarding } = useProfileContext();
  const { run, loading, error, result } = useNavisWorkflow("commute_analysis");

  const [origin, setOrigin] = useState<Location | null>(null);
  const [destination, setDestination] = useState<Location | null>(null);
  const [seeded, setSeeded] = useState(false);
  const ranForRef = useRef<string | null>(null);

  // Seed endpoints from the profile once it's available (set-during-render).
  if (!seeded && ready && profile) {
    setSeeded(true);
    setOrigin(profile.homeAreaLocation ?? profile.cityLocation ?? null);
    setDestination(profile.officeLocationResolved ?? null);
  }

  useEffect(() => {
    if (!origin || !destination) return;
    const key = `${origin.id}->${destination.id}`;
    if (ranForRef.current === key) return;
    ranForRef.current = key;
    void run(`Commute from ${origin.name} to ${destination.name}`, {
      origin,
      destination,
    });
  }, [origin, destination, run]);

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
          <Navigation className="size-6 text-indigo-500" />
        </div>
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            Set up your profile first
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Add your home area and office and we&apos;ll estimate your commute.
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
          Commute
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Travel time and distance between two places, by mode.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400">
            From
          </label>
          <LocationSearch
            value={origin?.label ?? ""}
            placeholder="Origin (e.g. home area)"
            onSelect={setOrigin}
            near={profile.cityLocation}
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400">
            To
          </label>
          <LocationSearch
            value={destination?.label ?? ""}
            placeholder="Destination (e.g. office)"
            onSelect={setDestination}
            near={profile.cityLocation}
          />
        </div>
      </div>

      {(!origin || !destination) && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Pick an origin and a destination to see commute estimates.
        </p>
      )}

      {origin && destination && loading && (
        <div className="py-12 text-center text-sm text-zinc-500 dark:text-zinc-400">
          Estimating your commute…
        </div>
      )}

      {origin && destination && !loading && error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/30 dark:text-rose-300">
          {error}
        </div>
      )}

      {origin && destination && !loading && !error && result && (
        <CommuteGrid items={toCommutes(result as Record<string, unknown>)} />
      )}
    </div>
  );
}
