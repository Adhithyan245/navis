"use client";
/**
 * /essentials — city-specific relocation essentials checklist.
 *
 * Runs the `essentials_checklist` workflow (auto-injecting the persisted
 * profile) and renders the returned corpus items as a ChecklistGrid. Per-item
 * progress is owned by ChecklistContext, keyed off each chunk's frontmatter id.
 */
import { useEffect, useRef } from "react";
import { ClipboardList } from "lucide-react";

import { ChecklistGrid } from "@/components/runtime/ChecklistGrid";
import { Button } from "@/components/ui/button";
import { useNavisWorkflow } from "@/hooks/useNavisWorkflow";
import { useProfileContext } from "@/lib/profile/context";
import { hasGeneratedItems, toChecklistItems } from "@/lib/runtime/payload";

export default function EssentialsPage() {
  const { ready, profile, restoreOnboarding } = useProfileContext();
  const { run, loading, error, result } = useNavisWorkflow("essentials_checklist");
  // Fire the workflow once per profile identity (re-runs if the profile
  // changes, e.g. city edited). Ref guard avoids duplicate runs on re-render.
  const ranForRef = useRef<string | null>(null);

  useEffect(() => {
    if (!ready || !profile) return;
    const key = `${profile.city}|${profile.moveStage}|${profile.household}`;
    if (ranForRef.current === key) return;
    ranForRef.current = key;
    void run(`Essentials checklist for ${profile.city || "my new city"}`);
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
          <ClipboardList className="size-6 text-indigo-500" />
        </div>
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            Set up your profile first
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Tell Navis about your move and we&apos;ll build a checklist tailored
            to your city and stage.
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
          Your essentials
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          What to sort out{profile.city ? ` in ${profile.city}` : ""}. Progress
          is saved to your account.
        </p>
      </header>

      {loading && (
        <div className="py-12 text-center text-sm text-zinc-500 dark:text-zinc-400">
          Building your checklist… The first time for a new place takes a few seconds.
        </div>
      )}

      {!loading && error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/30 dark:text-rose-300">
          {error}
        </div>
      )}

      {!loading && !error && result && (
        <>
          <ChecklistGrid items={toChecklistItems(result as Record<string, unknown>)} />
          {hasGeneratedItems(result as Record<string, unknown>) && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Local items for {profile.city} were compiled by AI from general knowledge. Rules and
              names change, so check official sources before acting.
            </p>
          )}
        </>
      )}
    </div>
  );
}
