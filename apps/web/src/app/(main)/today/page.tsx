"use client";
/**
 * /today — the newcomer hub. Eight agents report on the user's place at
 * once: weather, what's on, tech & community, getting around, getting here,
 * money, safety & health, and local know-how. Cards fill in as each agent
 * finishes; an agent with little to show says so positively and suggests
 * what to try instead.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, MapPin, RefreshCw, Sparkles } from "lucide-react";

import { SectionBlock } from "@/components/runtime/ResultStream";
import { Button } from "@/components/ui/button";
import { runtimeClient } from "@/lib/runtime/client";
import type { RuntimeSection } from "@/lib/runtime/events";
import { useProfileContext } from "@/lib/profile/context";
import { cn } from "@/lib/utils";

// Display order and the "see more" destination for each agent's card.
const CARDS: Array<{ kind: string; title: string; href?: string; wide?: boolean }> = [
  { kind: "weather", title: "Weather" },
  { kind: "safety", title: "Safety & health", href: "/care" },
  { kind: "events", title: "What's on", href: "/events", wide: true },
  { kind: "tech", title: "Tech & community", wide: true },
  { kind: "transit", title: "Getting around", href: "/commute" },
  { kind: "arrival", title: "Getting here" },
  { kind: "money", title: "Money" },
  { kind: "culture", title: "Know before you go" },
];

type Phase = "idle" | "loading" | "done" | "error";

export default function TodayPage() {
  const { ready, profile, restoreOnboarding } = useProfileContext();
  const [sections, setSections] = useState<Record<string, RuntimeSection>>({});
  const [summary, setSummary] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [runKey, setRunKey] = useState(0);
  const ranFor = useRef<string | null>(null);

  const city = profile?.city || profile?.cityLocation?.city || profile?.cityLocation?.name || "";

  useEffect(() => {
    if (!ready || !profile || !city) return;
    const key = `${city}|${profile.cityLocation?.lat}|${runKey}`;
    if (ranFor.current === key) return;
    ranFor.current = key;
    const controller = new AbortController();
    const userContext = profile as unknown as Record<string, unknown>;
    (async () => {
      setPhase("loading");
      setSections({});
      setSummary(null);
      try {
        for await (const event of runtimeClient.todayStream(userContext, { signal: controller.signal })) {
          if (event.event === "partial_result" && event.data.section && typeof event.data.section === "object") {
            const s = event.data.section as RuntimeSection;
            setSections((prev) => ({ ...prev, [s.kind]: s }));
          } else if (event.event === "final_result") {
            const finalSections = Array.isArray(event.data.sections) ? (event.data.sections as RuntimeSection[]) : [];
            setSections(Object.fromEntries(finalSections.map((s) => [s.kind, s])));
            setSummary(typeof event.data.summary === "string" ? event.data.summary : null);
            setPhase("done");
          } else if (event.event === "error") {
            setPhase("error");
          }
        }
      } catch {
        if (!controller.signal.aborted) setPhase("error");
      }
    })();
    return () => {
      controller.abort();
      ranFor.current = null;
    };
  }, [ready, profile, city, runKey]);

  const today = useMemo(
    () => new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }),
    []
  );

  if (!ready) return <div className="py-12 text-sm text-zinc-500">Loading…</div>;

  if (!profile || !city) {
    return (
      <div className="mx-auto flex max-w-xl flex-col items-center gap-5 py-16 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-indigo-50 dark:bg-indigo-500/10">
          <MapPin className="size-6 text-indigo-500" />
        </span>
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">Where are you landing?</h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Tell Navis your city, town or island and this page fills with everything you need there today.
          </p>
        </div>
        <Button onClick={restoreOnboarding}>Choose your place</Button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full min-w-0 max-w-6xl flex-col gap-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">{today}</p>
          <h1 className="text-3xl font-semibold tracking-[-0.02em] text-zinc-900 sm:text-4xl dark:text-zinc-50">
            Today in <span className="text-gradient">{city}</span>
          </h1>
        </div>
        <Button variant="outline" size="sm" onClick={() => setRunKey((k) => k + 1)} disabled={phase === "loading"}>
          <RefreshCw className={cn(phase === "loading" && "animate-spin")} /> Refresh
        </Button>
      </header>

      {summary && (
        <p className="flex items-start gap-2 rounded-2xl border border-indigo-200/60 bg-indigo-50/70 px-4 py-3 text-[15px] text-indigo-950 dark:border-indigo-400/15 dark:bg-indigo-500/10 dark:text-indigo-100">
          <Sparkles className="mt-0.5 size-4 shrink-0 text-indigo-500" aria-hidden />
          {summary}
        </p>
      )}

      {phase === "error" && (
        <p className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-600 dark:border-white/10 dark:bg-white/[0.03] dark:text-zinc-300">
          Part of today&apos;s overview didn&apos;t load. Press Refresh to try again; everything else below is up to date.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {CARDS.map((card) => {
          const section = sections[card.kind];
          return (
            <article
              key={card.kind}
              className={cn(
                "min-w-0 rounded-2xl border border-zinc-200/80 bg-white/90 p-5 shadow-soft dark:border-white/[0.07] dark:bg-zinc-900/70",
                card.wide && "md:col-span-2"
              )}
            >
              <div className="mb-3 flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">{card.title}</h2>
                {card.href && section && section.status !== "unavailable" && (
                  <Link href={card.href} className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                    See more <ArrowRight className="size-3" />
                  </Link>
                )}
              </div>
              {section ? (
                <SectionBlock section={section} limit={card.wide ? 3 : 4} hideTitle />
              ) : phase === "loading" ? (
                <div className="space-y-2" role="status" aria-label={`Loading ${card.title}`}>
                  <div className="h-4 w-2/3 rounded bg-zinc-100 animate-shimmer bg-gradient-to-r from-zinc-100 via-zinc-200/70 to-zinc-100 bg-[length:200%_100%] dark:from-zinc-800 dark:via-zinc-700 dark:to-zinc-800" />
                  <div className="h-16 rounded-xl bg-zinc-100 animate-shimmer bg-gradient-to-r from-zinc-100 via-zinc-200/70 to-zinc-100 bg-[length:200%_100%] dark:from-zinc-800 dark:via-zinc-700 dark:to-zinc-800" />
                </div>
              ) : (
                <p className="text-sm text-zinc-500">Nothing here yet. Press Refresh to check again.</p>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
