"use client";
/**
 * useNavisWorkflow — drives a single POST /v2/workflow/{name} run via the
 * central runtime client. Sibling of useNavisQuery, but skips intent
 * routing: the caller names the workflow up front.
 *
 * State machine:  idle -> streaming -> done | error | cancelled
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { runtimeClient, RuntimeApiError } from "@/lib/runtime/client";
import type { FinalResultPayload, RuntimeEvent } from "@/lib/runtime/events";
import { isErrorEvent, isFinalResult } from "@/lib/runtime/events";
import { useProfileContext } from "@/lib/profile/context";

export type WorkflowStatus =
  | "idle"
  | "streaming"
  | "done"
  | "error"
  | "cancelled";

export interface UseNavisWorkflowState {
  status: WorkflowStatus;
  query: string;
  events: RuntimeEvent[];
  result: FinalResultPayload | null;
  error: string | null;
}

export interface UseNavisWorkflowResult {
  run: (query: string, userContext?: Record<string, unknown>) => Promise<void>;
  cancel: () => void;
  reset: () => void;
  loading: boolean;
  status: WorkflowStatus;
  query: string;
  events: RuntimeEvent[];
  result: FinalResultPayload | null;
  error: string | null;
}

const INITIAL: UseNavisWorkflowState = {
  status: "idle",
  query: "",
  events: [],
  result: null,
  error: null,
};

export function useNavisWorkflow(workflowName: string): UseNavisWorkflowResult {
  const [state, setState] = useState<UseNavisWorkflowState>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  // Auto-inject the persisted profile into every run as `user_context`,
  // exactly like useNavisQuery. Null pre-onboarding -> just the overrides.
  const { profile } = useProfileContext();
  // Strict Mode (dev) runs unmount→remount on every mount. Callers guard
  // their auto-run with a run-once ref, so a run aborted by that synthetic
  // unmount would never restart and the page would sit in "streaming"
  // forever. Remember the interrupted run's args and resume it on remount.
  const lastArgsRef = useRef<{ query: string; userContext: Record<string, unknown> } | null>(null);
  const interruptedRef = useRef<{ query: string; userContext: Record<string, unknown> } | null>(null);
  const runRef = useRef<UseNavisWorkflowResult["run"] | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    const resume = interruptedRef.current;
    interruptedRef.current = null;
    if (resume) void runRef.current?.(resume.query, resume.userContext);
    return () => {
      mountedRef.current = false;
      if (abortRef.current) {
        interruptedRef.current = lastArgsRef.current;
        abortRef.current.abort();
        abortRef.current = null;
      }
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

  const run = useCallback(
    async (
      query: string,
      userContext: Record<string, unknown> = {}
    ): Promise<void> => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      lastArgsRef.current = { query, userContext };

      setState({ ...INITIAL, query, status: "streaming" });

      // Profile (base) merged with caller overrides (top) — same precedence
      // as useNavisQuery.
      const mergedContext: Record<string, unknown> = {
        ...((profile ?? {}) as Record<string, unknown>),
        ...userContext,
      };

      try {
        const stream = runtimeClient.workflowStream(
          workflowName,
          query,
          mergedContext,
          {
            signal: controller.signal,
            onMalformed: (line, reason) => {
              if (!mountedRef.current) return;
              console.warn("[useNavisWorkflow] malformed line", reason, line);
            },
          }
        );

        for await (const event of stream) {
          if (!mountedRef.current || controller.signal.aborted) break;

          setState((prev) => ({ ...prev, events: [...prev.events, event] }));

          if (isFinalResult(event)) {
            setState((prev) => ({ ...prev, result: event.data, status: "done" }));
            continue;
          }
          if (isErrorEvent(event)) {
            setState((prev) => ({
              ...prev,
              error: event.data.message,
              status: "error",
            }));
          }
        }

        // Stream ended cleanly. If still "streaming", no final_result arrived.
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
    [profile, workflowName]
  );

  useEffect(() => {
    runRef.current = run;
  }, [run]);

  return {
    run,
    cancel,
    reset,
    loading: state.status === "streaming",
    status: state.status,
    query: state.query,
    events: state.events,
    result: state.result,
    error: state.error,
  };
}
