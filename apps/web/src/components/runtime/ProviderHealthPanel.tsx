"use client";
/**
 * ProviderHealthPanel — operational visibility for /providers/budget.
 *
 * Surfaces ONLY operational data (availability, latency, quota state). Does
 * NOT expose orchestration internals (no node ids, no graph topology, no
 * workflow names). Per the invisible-orchestration rule, the panel answers
 * "what infrastructure is healthy" — never "what is the runtime doing."
 *
 * Auto-refreshes every 30s, pauses in hidden tabs.
 */
import { AlertCircle, CheckCircle2, KeyRound, RefreshCw, XCircle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useProviderStatus,
  type ProviderEntry,
} from "@/hooks/useProviderStatus";
import { cn } from "@/lib/utils";

export function ProviderHealthPanel() {
  const { providers, loading, error, lastFetchedAt, refresh } =
    useProviderStatus();

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="text-sm">Provider health</CardTitle>
        <div className="flex items-center gap-3">
          {lastFetchedAt !== null && (
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {formatRelative(lastFetchedAt)}
            </span>
          )}
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => void refresh()}
            disabled={loading}
            aria-label="Refresh provider status"
          >
            <RefreshCw className={cn(loading && "animate-spin")} />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {error && !providers && (
          <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>
        )}
        {!providers && !error && (
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Checking providers…
          </p>
        )}
        {providers && (
          <ul className="-mx-2.5 space-y-0.5">
            {Object.entries(providers)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([name, entry]) => (
                <ProviderRow key={name} name={name} entry={entry} />
              ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function ProviderRow({ name, entry }: { name: string; entry: ProviderEntry }) {
  const status = entry.health?.status ?? "unknown";
  const latency = entry.health?.latency_ms;
  const note = typeof entry.health?.note === "string" ? entry.health.note : "";
  const fallback = entry.health?.fallback_available === true;
  const quotaWarning =
    entry.health?.quota_warning === true || entry.budget?.quota_warning === true;
  const remaining = entry.budget?.daily_remaining;

  return (
    <li className="flex items-center justify-between gap-3 rounded-xl px-2.5 py-2 transition-colors hover:bg-zinc-50 dark:hover:bg-white/[0.03]">
      <div className="flex items-center gap-2 min-w-0">
        <StatusIcon status={status} />
        <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100 truncate">
          {name}
        </span>
        <StatusBadge status={status} />
        {fallback && status !== "not_configured" && (
          <span
            title="A backup provider is available if this one fails"
            className="hidden text-[10px] text-zinc-400 sm:inline dark:text-zinc-500"
          >
            + backup
          </span>
        )}
      </div>
      <div
        className="flex items-center gap-2 text-[11px] text-zinc-500 dark:text-zinc-400"
        title={note || undefined}
      >
        {status === "not_configured" && (
          <span className="text-zinc-500 dark:text-zinc-400">no key</span>
        )}
        {status !== "not_configured" && typeof latency === "number" && latency > 0 && (
          <span>{latency.toFixed(0)}ms</span>
        )}
        {typeof remaining === "number" && (
          <span
            className={cn(
              quotaWarning && "text-rose-600 dark:text-rose-400 font-medium"
            )}
          >
            {remaining} left today
          </span>
        )}
      </div>
    </li>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "healthy") {
    return <CheckCircle2 className="size-3.5 text-emerald-500" />;
  }
  if (status === "degraded" || status === "rate_limited" || status === "quota_exceeded") {
    return <AlertCircle className="size-3.5 text-amber-500" />;
  }
  if (status === "not_configured") {
    return <KeyRound className="size-3.5 text-zinc-400" />;
  }
  if (
    status === "invalid_credentials" ||
    status === "unreachable" ||
    status === "offline" ||
    status === "timeout" ||
    status === "error"
  ) {
    return <XCircle className="size-3.5 text-rose-500" />;
  }
  return <AlertCircle className="size-3.5 text-zinc-400" />;
}

function StatusBadge({ status }: { status: string }) {
  // Compact label for states the operator needs to action on. Healthy states
  // get no badge to keep the row visually quiet.
  if (status === "not_configured") {
    return (
      <span className="rounded-full bg-zinc-100 px-1.5 py-0.5 text-[9px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
        not configured
      </span>
    );
  }
  if (status === "invalid_credentials") {
    return (
      <span className="rounded-full bg-rose-50 px-1.5 py-0.5 text-[9px] font-medium text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
        bad credentials
      </span>
    );
  }
  return null;
}

function formatRelative(ts: number): string {
  const seconds = Math.floor((Date.now() - ts) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}
