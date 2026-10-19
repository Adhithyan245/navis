"use client";
/**
 * QueryConsole — input + result stream + voice button.
 *
 * Receives streaming state from its parent (QueryWorkspace) so the same
 * partials/final/error can drive the map alongside the textual results.
 * Owns ONLY the in-progress text input and submission gestures.
 *
 * Invisible orchestration: no "calling provider X" / "executing node Y" /
 * "running agent Z" copy anywhere. The user sees Working/Refining/Final.
 */
import { useRef, useState } from "react";
import { ArrowUp, Loader2, Search, X } from "lucide-react";

import { ResultStream } from "@/components/runtime/ResultStream";
import { VoiceMicButton } from "@/components/runtime/VoiceMicButton";
import { Button } from "@/components/ui/button";
import type { UseNavisQueryResult } from "@/hooks/useNavisQuery";
import { useProfileContext } from "@/lib/profile/context";

/** Starter questions for the user's own place; global examples otherwise. */
function suggestionsFor(city: string | undefined, area: string | undefined): string[] {
  if (!city) {
    return [
      "best cafes in Lisbon",
      "events in Tokyo this weekend",
      "what should I do first after moving to Berlin",
    ];
  }
  const near = area && area !== city ? area : city;
  return [
    `coffee shops near ${near}`,
    `events in ${city} this weekend`,
    `what should I do first after moving to ${city}`,
    `which neighborhood in ${city} is good for families`,
  ];
}

interface QueryConsoleProps {
  /** State + actions from useNavisQuery, hoisted to the parent so the map can share it. */
  state: UseNavisQueryResult;
}

export function QueryConsole({ state }: QueryConsoleProps) {
  const { status, partials, final, error, query, submit, cancel, reset } = state;
  const { profile } = useProfileContext();
  const suggestions = suggestionsFor(profile?.city || undefined, profile?.homeArea || undefined);
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const streaming = status === "streaming";

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || streaming) return;
    void submit(text);
  };

  const onTranscript = (text: string) => {
    if (streaming) return;
    const query = text.slice(0, 2000);
    setInput(query);
    void submit(query);
  };

  const onSuggestion = (text: string) => {
    if (streaming) return;
    setInput(text);
    void submit(text);
    inputRef.current?.focus();
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <form
        onSubmit={onSubmit}
        className="group/bar relative flex items-center gap-2 rounded-2xl border border-zinc-200/80 bg-white/95 p-2 pl-4 shadow-glow transition-[border-color,box-shadow] focus-within:border-indigo-300 focus-within:ring-4 focus-within:ring-indigo-500/10 dark:border-white/[0.08] dark:bg-zinc-900/80 dark:focus-within:border-indigo-400/40"
      >
        <Search aria-hidden className="size-5 shrink-0 text-zinc-400 transition-colors group-focus-within/bar:text-indigo-500" />
        <input
          ref={inputRef}
          maxLength={2000}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything about a place — cafes, events, work spots…"
          aria-label="Query"
          className="min-w-0 flex-1 bg-transparent px-1 py-2.5 text-base outline-none placeholder:text-zinc-400 dark:text-zinc-100"
          disabled={streaming}
        />
        {streaming ? (
          <Button
            type="button"
            variant="ghost"
            size="lg"
            onClick={cancel}
            aria-label="Cancel current request"
          >
            <X />
            Cancel
          </Button>
        ) : (
          <Button
            type="submit"
            variant="default"
            size="lg"
            disabled={!input.trim()}
            aria-label="Send query"
          >
            <span className="hidden sm:inline">Ask</span>
            <ArrowUp />
          </Button>
        )}
      </form>

      {/* Voice + suggestions row */}
      {status === "idle" && (
        <div className="flex flex-wrap items-start gap-3">
          <VoiceMicButton onTranscript={onTranscript} />
          <div className="flex flex-1 flex-wrap gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => onSuggestion(s)}
                type="button"
                className="rounded-full border border-zinc-200/80 bg-white/70 px-3.5 py-1.5 text-[13px] text-zinc-600 shadow-sm backdrop-blur transition-all hover:-translate-y-px hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 dark:border-white/[0.08] dark:bg-zinc-900/60 dark:text-zinc-300 dark:hover:border-indigo-400/40 dark:hover:bg-indigo-500/10 dark:hover:text-indigo-200"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Active query indicator */}
      {query && status !== "idle" && (
        <div className="flex items-center justify-between rounded-xl border border-zinc-200/80 bg-white/60 px-4 py-2.5 text-sm backdrop-blur dark:border-white/[0.07] dark:bg-zinc-900/50">
          <span className="flex items-center gap-2 text-zinc-700 dark:text-zinc-300">
            {streaming && <Loader2 className="size-3 animate-spin" />}
            <span className="font-medium">{query}</span>
          </span>
          {status !== "streaming" && (
            <button
              onClick={reset}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400"
            >
              New query
            </button>
          )}
        </div>
      )}

      {status === "error" && error && (
        <div
          role="alert"
          className="flex items-start justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900 dark:border-rose-900/40 dark:bg-rose-950/30 dark:text-rose-200"
        >
          <span>{error}</span>
          <button
            onClick={() => query && void submit(query)}
            className="shrink-0 text-xs font-medium underline-offset-2 hover:underline"
          >
            Retry
          </button>
        </div>
      )}

      {status === "cancelled" && (
        <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900/50 dark:text-zinc-400">
          Cancelled. Send a new query to start over.
        </div>
      )}

      <ResultStream partials={partials} final={final} streaming={streaming} />
    </div>
  );
}
