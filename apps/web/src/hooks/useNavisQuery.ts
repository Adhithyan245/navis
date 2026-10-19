"use client";
/**
 * useNavisQuery — drives a single POST /v2/query run via the central
 * runtime client. Single source of truth for the conversational page's
 * streaming state.
 *
 * State machine:  idle -> streaming -> done | error | cancelled
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { runtimeClient, RuntimeApiError } from "@/lib/runtime/client";
import type {
  FinalResultPayload,
  PartialResultPayload,
} from "@/lib/runtime/events";
import { isErrorEvent, isFinalResult, isPartialResult } from "@/lib/runtime/events";
import { useProfileContext } from "@/lib/profile/context";

export type QueryStatus = "idle" | "streaming" | "done" | "error" | "cancelled";

export interface UseNavisQueryState {
  status: QueryStatus;
  query: string;
  partials: PartialResultPayload[];
  final: FinalResultPayload | null;
  error: string | null;
  heartbeats: number;
  malformed: number;
}

export interface UseNavisQueryResult extends UseNavisQueryState {
  submit: (query: string, userContext?: Record<string, unknown>) => Promise<void>;
  cancel: () => void;
  reset: () => void;
}

const INITIAL: UseNavisQueryState = {
  status: "idle",
  query: "",
  partials: [],
  final: null,
  error: null,
  heartbeats: 0,
  malformed: 0,
};

export function useNavisQuery(): UseNavisQueryResult {
  const [state, setState] = useState<UseNavisQueryState>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  // Auto-inject the persisted profile into every outgoing query as
  // `user_context`. When no profile exists (first visit / pre-onboarding),
  // this is null and the outgoing user_context is just the caller's
  // overrides (typically {}).
  const { profile } = useProfileContext();

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, []);

  const cancel = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setState((prev) =>
      prev.status === "streaming" ? { ...prev, status: "cancelled" } : prev
    );
  }, []);

  const reset = useCallback(() => {
    cancel();
    setState(INITIAL);
  }, [cancel]);

  const submit = useCallback(
    async (
      query: string,
      userContext: Record<string, unknown> = {}
    ): Promise<void> => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setState({ ...INITIAL, query, status: "streaming" });

      // Merge profile (base) with caller-provided overrides (top). Profile
      // fields are spread first so callers can override individual keys
      // if they ever need to (no current callers do).
      const mergedContext: Record<string, unknown> = {
        ...((profile ?? {}) as Record<string, unknown>),
        ...userContext,
      };

      try {
        const stream = runtimeClient.queryStream(query, mergedContext, {
          signal: controller.signal,
          onMalformed: (line, reason) => {
            if (!mountedRef.current) return;
            console.warn("[useNavisQuery] malformed line", reason, line);
            setState((prev) => ({ ...prev, malformed: prev.malformed + 1 }));
          },
        });

        for await (const event of stream) {
          if (!mountedRef.current || controller.signal.aborted) break;

          if (isPartialResult(event)) {
            setState((prev) => ({
              ...prev,
              partials: [...prev.partials, event.data],
            }));
            continue;
          }
          if (isFinalResult(event)) {
            setState((prev) => ({
              ...prev,
              final: event.data,
              status: "done",
            }));
            continue;
          }
          if (isErrorEvent(event)) {
            setState((prev) => ({
              ...prev,
              error: event.data.message,
              status: "error",
            }));
            continue;
          }
          if (event.event === "stream_heartbeat") {
            setState((prev) => ({ ...prev, heartbeats: prev.heartbeats + 1 }));
          }
        }

        // Stream ended cleanly. If still in "streaming", no final_result arrived.
        if (!mountedRef.current) return;
        setState((prev) =>
          prev.status === "streaming"
            ? {
                ...prev,
                status: "error",
                error:
                  "The connection ended before a final result arrived. Try again.",
              }
            : prev
        );
      } catch (err) {
        if (!mountedRef.current || controller.signal.aborted) return;
        const message =
          err instanceof RuntimeApiError
            ? `Request failed (${err.status}). Try again.`
            : err instanceof Error
            ? "Something went wrong reaching the assistant. Try again."
            : "Unexpected error. Try again.";
        setState((prev) => ({ ...prev, status: "error", error: message }));
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [profile]
  );

  return { ...state, submit, cancel, reset };
}
