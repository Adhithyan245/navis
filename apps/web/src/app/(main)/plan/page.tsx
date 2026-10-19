"use client";
/**
 * /plan — phased relocation plan tailored to the user's profile.
 *
 * Runs the `relocation_plan` workflow (auto-injecting the persisted profile)
 * and renders the returned corpus items as a PlanTimeline grouped by phase.
 * Per-item progress overlays from ChecklistContext via the shared item id.
 */
import { useEffect, useRef } from "react";
import { Map as MapIcon } from "lucide-react";

import { PlanTimeline, type PlanItem } from "@/components/runtime/PlanTimeline";
import { Button } from "@/components/ui/button";
import { useNavisWorkflow } from "@/hooks/useNavisWorkflow";
import { useProfileContext } from "@/lib/profile/context";

interface ChunkView {
  frontmatter?: Record<string, unknown>;
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}

function toPlanItems(result: Record<string, unknown> | null): PlanItem[] {
  if (!result) return [];
  const chunks = result.chunks;
  if (!Array.isArray(chunks)) return [];

  const items: PlanItem[] = [];
  for (const raw of chunks as ChunkView[]) {
    const fm = raw?.frontmatter;
    if (!fm || typeof fm !== "object") continue;
    const f = fm as Record<string, unknown>;
    const id = str(f.id);
    const title = str(f.title);
    if (!id || !title) continue;
    items.push({
      id,
      title,
      urgency: str(f.urgency) ?? "medium",
      stage: str(f.stage) ?? "universal",
    });
  }
  return items;
}

export default function PlanPage() {
  const { ready, profile, restoreOnboarding } = useProfileContext();
  const { run, loading, error, result } = useNavisWorkflow("relocation_plan");
  const ranForRef = useRef<string | null>(null);

  useEffect(() => {
    if (!ready || !profile) return;
    const key = `${profile.city}|${profile.moveStage}|${profile.household}|${profile.budgetBand}`;
    if (ranForRef.current === key) return;
    ranForRef.current = key;
    void run(`Relocation plan for ${profile.city || "my new city"}`);
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
          <MapIcon className="size-6 text-indigo-500" />
        </div>
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            Set up your profile first
          </h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Tell Navis about your move and we&apos;ll build a phased plan tailored
            to your city, stage, and household.
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
          Your relocation plan
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          A phased path{profile.city ? ` to settling into ${profile.city}` : ""}.
          Status carries over from your essentials checklist.
        </p>
      </header>

      {loading && (
        <div className="py-12 text-center text-sm text-zinc-500 dark:text-zinc-400">
          Building your plan…
        </div>
      )}

      {!loading && error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/30 dark:text-rose-300">
          {error}
        </div>
      )}

      {!loading && !error && result && (
        <PlanTimeline items={toPlanItems(result as Record<string, unknown>)} />
      )}
    </div>
  );
}
