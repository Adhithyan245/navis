"use client";
/**
 * DashboardHero — top-of-home summary card. Greets the user, surfaces their
 * move stage, checklist progress (done / total), and the top 3 priority
 * essentials, with quick links into /plan and /essentials.
 *
 * Sources: ProfileContext (identity + stage), ChecklistContext (progress
 * overlay), and the essentials_checklist workflow (corpus items). Read-only
 * — status changes happen on the dedicated /essentials page.
 */
import { useEffect, useMemo, useRef } from "react";
import Link from "next/link";
import { ArrowRight, ClipboardList, Map as MapIcon } from "lucide-react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useNavisWorkflow } from "@/hooks/useNavisWorkflow";
import { useChecklistContext } from "@/lib/checklist/context";
import { useProfileContext } from "@/lib/profile/context";
import { MOVE_STAGES } from "@/lib/profile/schema";
import { cn } from "@/lib/utils";

interface ChunkView {
  frontmatter?: Record<string, unknown>;
}

interface EssentialItem {
  id: string;
  title: string;
  urgency: string;
}

const URGENCY_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}

function toItems(result: Record<string, unknown> | null): EssentialItem[] {
  if (!result) return [];
  const chunks = result.chunks;
  if (!Array.isArray(chunks)) return [];
  const items: EssentialItem[] = [];
  for (const raw of chunks as ChunkView[]) {
    const fm = raw?.frontmatter;
    if (!fm || typeof fm !== "object") continue;
    const f = fm as Record<string, unknown>;
    const id = str(f.id);
    const title = str(f.title);
    if (!id || !title) continue;
    items.push({ id, title, urgency: str(f.urgency) ?? "medium" });
  }
  return items;
}

const URGENCY_STYLES: Record<string, string> = {
  high: "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
  medium: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
  low: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
};

export function DashboardHero() {
  const { ready, profile, restoreOnboarding } = useProfileContext();
  const { checklist } = useChecklistContext();
  const { run, loading, error, result } = useNavisWorkflow("essentials_checklist");
  const ranForRef = useRef<string | null>(null);

  useEffect(() => {
    if (!ready || !profile) return;
    const key = `${profile.city}|${profile.moveStage}|${profile.household}`;
    if (ranForRef.current === key) return;
    ranForRef.current = key;
    void run(`Essentials checklist for ${profile.city || "my new city"}`);
  }, [ready, profile, run]);

  const items = useMemo(() => toItems(result as Record<string, unknown> | null), [result]);

  const topItems = useMemo(
    () =>
      [...items]
        .sort(
          (a, b) =>
            (URGENCY_RANK[b.urgency.toLowerCase()] ?? 0) -
            (URGENCY_RANK[a.urgency.toLowerCase()] ?? 0)
        )
        .slice(0, 3),
    [items]
  );

  const progress = useMemo(() => {
    const total = items.length;
    if (total === 0) return { done: 0, total: 0 };
    const done = items.filter(
      (it) => checklist.items[it.id]?.status === "done"
    ).length;
    return { done, total };
  }, [items, checklist]);

  if (!ready) {
    return (
      <Card>
        <CardContent className="p-5 text-sm text-zinc-500 dark:text-zinc-400">
          Loading your dashboard…
        </CardContent>
      </Card>
    );
  }

  if (!profile) {
    return (
      <Card>
        <CardContent className="flex flex-col items-start gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
              Set up your Navis profile
            </h2>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Tell Navis about your move to get a tailored plan and checklist.
            </p>
          </div>
          <Button onClick={restoreOnboarding}>Set up profile</Button>
        </CardContent>
      </Card>
    );
  }

  const stageLabel = MOVE_STAGES.find((s) => s.value === profile.moveStage)?.label;
  const greetingPlace = profile.city ? ` in ${profile.city}` : "";

  return (
    <Card>
      <CardContent className="flex flex-col gap-5 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
              Welcome back{greetingPlace}
            </h2>
            {stageLabel && (
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                Move stage: <span className="font-medium">{stageLabel}</span>
              </p>
            )}
          </div>
          {progress.total > 0 && (
            <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
              {progress.done} / {progress.total} essentials done
            </span>
          )}
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            Top priorities
          </h3>
          <div className="mt-2">
            {loading && (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                Loading your essentials…
              </p>
            )}
            {!loading && error && (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                Couldn&apos;t load your essentials right now.
              </p>
            )}
            {!loading && !error && topItems.length === 0 && (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                No essentials yet for your city.
              </p>
            )}
            {!loading && !error && topItems.length > 0 && (
              <ul className="flex flex-col gap-2">
                {topItems.map((item) => {
                  const status = checklist.items[item.id]?.status ?? null;
                  return (
                    <li
                      key={item.id}
                      className="flex items-center justify-between gap-3 rounded-lg border border-zinc-200 bg-white px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900"
                    >
                      <span
                        className={cn(
                          "text-sm text-zinc-800 dark:text-zinc-200",
                          status === "done" &&
                            "line-through text-zinc-400 dark:text-zinc-500"
                        )}
                      >
                        {item.title}
                      </span>
                      <span
                        className={cn(
                          "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium",
                          URGENCY_STYLES[item.urgency.toLowerCase()] ??
                            "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
                        )}
                      >
                        {item.urgency}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Link
            href="/plan"
            className={cn(buttonVariants({ variant: "default", size: "sm" }))}
          >
            <MapIcon />
            Open plan
            <ArrowRight />
          </Link>
          <Link
            href="/essentials"
            className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
          >
            <ClipboardList />
            Open essentials
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
