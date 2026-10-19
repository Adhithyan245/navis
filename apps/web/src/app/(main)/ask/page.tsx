import { DashboardHero } from "@/components/runtime/DashboardHero";
import { QueryWorkspace } from "@/components/runtime/QueryWorkspace";

export const metadata = {
  title: "Ask Navis",
  description: "Navis runtime-backed conversational query interface",
};

// Server Component shell. The QueryWorkspace below owns all streaming state,
// and the map — every interactive concern lives below
// the 'use client' boundary inside that component.
export default function HomePage() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-2xl">
          <p className="mb-3 inline-flex items-center gap-2 rounded-full border border-indigo-200/70 bg-indigo-50/70 px-3 py-1 text-xs font-medium text-indigo-700 dark:border-indigo-400/20 dark:bg-indigo-500/10 dark:text-indigo-300">
            <span className="size-1.5 rounded-full bg-indigo-500" aria-hidden />
            Your city companion
          </p>
          <h1 className="text-4xl font-semibold tracking-[-0.03em] text-zinc-900 sm:text-5xl dark:text-zinc-50">
            Ask <span className="text-gradient">Navis</span> anything
          </h1>
          <p className="mt-3 text-[15px] leading-relaxed text-zinc-500 dark:text-zinc-400">
            Discover places, events, and workspaces near you. Results stream in
            live as Navis gathers them.
          </p>
        </div>
      </header>

      <QueryWorkspace />

      <DashboardHero />
    </div>
  );
}
