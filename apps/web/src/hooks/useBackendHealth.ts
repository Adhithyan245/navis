"use client";
/**
 * useBackendHealth — periodic ping of GET /health via the central runtime
 * client. Surfaces real backend reachability.
 *
 * State machine: "checking" -> "online" | "offline"
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { runtimeClient, RuntimeApiError } from "@/lib/runtime/client";

export type BackendStatus = "checking" | "online" | "offline";

export interface UseBackendHealthResult {
  status: BackendStatus;
  lastCheckedAt: number | null;
  lastError: string | null;
  refresh: () => Promise<void>;
}

export interface UseBackendHealthOptions {
  intervalMs?: number;
  timeoutMs?: number;
}

const DEFAULT_INTERVAL = 10_000;
const DEFAULT_TIMEOUT = 5_000;

export function useBackendHealth(
  options: UseBackendHealthOptions = {}
): UseBackendHealthResult {
  const { intervalMs = DEFAULT_INTERVAL, timeoutMs = DEFAULT_TIMEOUT } = options;
  const [status, setStatus] = useState<BackendStatus>("checking");
  const [lastCheckedAt, setLastCheckedAt] = useState<number | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const inFlightRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    inFlightRef.current?.abort();
    const controller = new AbortController();
    inFlightRef.current = controller;
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      await runtimeClient.getHealth(controller.signal);
      if (!mountedRef.current) return;
      setStatus("online");
      setLastError(null);
      setLastCheckedAt(Date.now());
    } catch (err) {
      if (!mountedRef.current) return;
      const message =
        err instanceof RuntimeApiError
          ? `Backend returned ${err.status}`
          : err instanceof Error && err.name === "AbortError"
          ? "Health check timed out"
          : "Backend unreachable";
      setStatus("offline");
      setLastError(message);
      setLastCheckedAt(Date.now());
    } finally {
      clearTimeout(timeoutId);
      if (inFlightRef.current === controller) inFlightRef.current = null;
    }
  }, [timeoutMs]);

  useEffect(() => {
    mountedRef.current = true;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      void refresh();
      if (intervalId === null) {
        intervalId = setInterval(() => {
          if (document.visibilityState === "visible") void refresh();
        }, intervalMs);
      }
    };

    const stop = () => {
      if (intervalId !== null) {
        clearInterval(intervalId);
        intervalId = null;
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") void refresh();
    };

    start();
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      mountedRef.current = false;
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
      inFlightRef.current?.abort();
      inFlightRef.current = null;
    };
  }, [intervalMs, refresh]);

  return { status, lastCheckedAt, lastError, refresh };
}
