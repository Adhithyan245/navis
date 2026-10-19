"use client";
/**
 * useProviderStatus — polls /providers/budget via the central runtime client.
 *
 * Auto-refreshes every `refreshMs`. Pauses in hidden tabs. Re-checks
 * immediately on tab focus so the panel doesn't show stale state.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { runtimeClient, RuntimeApiError } from "@/lib/runtime/client";

export interface ProviderHealthEntry {
  status?: string;
  last_checked?: number;
  latency_ms?: number;
  fallback_available?: boolean;
  quota_warning?: boolean;
  [key: string]: unknown;
}

export interface ProviderBudgetEntry {
  daily_used?: number;
  daily_remaining?: number;
  per_minute_limit?: number;
  quota_warning?: boolean;
  [key: string]: unknown;
}

export interface ProviderEntry {
  health: ProviderHealthEntry;
  budget: ProviderBudgetEntry;
}

export type ProviderMap = Record<string, ProviderEntry>;

export interface UseProviderStatusResult {
  providers: ProviderMap | null;
  loading: boolean;
  error: string | null;
  lastFetchedAt: number | null;
  refresh: () => Promise<void>;
}

export interface UseProviderStatusOptions {
  refreshMs?: number;
  enabled?: boolean;
}

const DEFAULT_REFRESH_MS = 30_000;

export function useProviderStatus(
  options: UseProviderStatusOptions = {}
): UseProviderStatusResult {
  const { refreshMs = DEFAULT_REFRESH_MS, enabled = true } = options;
  const [providers, setProviders] = useState<ProviderMap | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  const refresh = useCallback(async (): Promise<void> => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    try {
      const data = await runtimeClient.getProviderHealth<ProviderMap>(
        controller.signal
      );
      if (!mountedRef.current || controller.signal.aborted) return;
      setProviders(data);
      setError(null);
      setLastFetchedAt(Date.now());
    } catch (err) {
      if (!mountedRef.current || controller.signal.aborted) return;
      const message =
        err instanceof RuntimeApiError
          ? `Provider status unavailable (${err.status}).`
          : "Provider status unavailable.";
      setError(message);
    } finally {
      if (mountedRef.current && abortRef.current === controller) {
        setLoading(false);
        abortRef.current = null;
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) return;

    let intervalId: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      void refresh();
      if (intervalId === null) {
        intervalId = setInterval(() => {
          if (document.visibilityState === "visible") {
            void refresh();
          }
        }, refreshMs);
      }
    };

    const stop = () => {
      if (intervalId !== null) {
        clearInterval(intervalId);
        intervalId = null;
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void refresh();
      }
    };

    start();
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      mountedRef.current = false;
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, [enabled, refreshMs, refresh]);

  return { providers, loading, error, lastFetchedAt, refresh };
}
