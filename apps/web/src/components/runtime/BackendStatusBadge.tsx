"use client";
/**
 * BackendStatusBadge — small inline pill reflecting real backend reachability.
 *
 * Three visual states:
 *   * checking — neutral, pulsing dot. First load.
 *   * online   — green dot. /health responding.
 *   * offline  — red dot + error tooltip. /health unreachable / timed out.
 *
 * Never lies. If the backend is offline, the badge says so.
 */
import { useBackendHealth } from "@/hooks/useBackendHealth";
import { getRuntimeConfig } from "@/lib/runtime/config";
import { cn } from "@/lib/utils";

export function BackendStatusBadge() {
  const { status, lastError } = useBackendHealth();
  const { apiBaseUrl } = getRuntimeConfig();

  const label =
    status === "checking"
      ? "Checking…"
      : status === "online"
      ? "Backend online"
      : "Backend offline";

  return (
    <div
      role="status"
      aria-live="polite"
      title={
        status === "offline" && lastError
          ? `${lastError} (${apiBaseUrl})`
          : apiBaseUrl
      }
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium",
        status === "online" &&
          "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-300",
        status === "offline" &&
          "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/30 dark:text-rose-300",
        status === "checking" &&
          "border-zinc-200 bg-zinc-50 text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400"
      )}
    >
      <span
        aria-hidden
        className={cn(
          "size-1.5 rounded-full",
          status === "online" && "bg-emerald-500",
          status === "offline" && "bg-rose-500",
          status === "checking" && "animate-pulse bg-zinc-400"
        )}
      />
      <span>{label}</span>
    </div>
  );
}
