"use client";
/**
 * useVoiceCapture — real microphone capture via MediaRecorder.
 *
 * Lifecycle:
 *   idle → requesting → recording → uploading → done | error
 *
 * After upload the backend transcribes the clip (Groq Whisper) and the
 * response is exposed as `result`. When it contains a transcript, the
 * optional `onTranscript` callback fires once so the caller can run it as
 * a query.
 *
 * Browser support: MediaRecorder is in all modern browsers. We feature-detect
 * and surface a clear error when unavailable.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { runtimeClient, RuntimeApiError } from "@/lib/runtime/client";
import type { VoiceUploadResult } from "@/lib/runtime/client";

export type VoiceStatus =
  | "idle"
  | "requesting_permission"
  | "recording"
  | "uploading"
  | "done"
  | "error";

export interface UseVoiceCaptureState {
  status: VoiceStatus;
  error: string | null;
  result: VoiceUploadResult | null;
  /** Duration in seconds of the in-progress recording. */
  elapsedSeconds: number;
}

export interface UseVoiceCaptureResult extends UseVoiceCaptureState {
  /** Begin recording. Resolves once the recording has started. */
  start: () => Promise<void>;
  /** Stop recording and upload. Resolves after upload completes (or fails). */
  stop: () => Promise<void>;
  /** Abort: stop recording, discard buffer, do NOT upload. */
  cancel: () => void;
  /** Clear result/error and return to idle. */
  reset: () => void;
}

export interface UseVoiceCaptureOptions {
  /** Called once per successful transcription with the transcript text. */
  onTranscript?: (text: string) => void;
}

const INITIAL: UseVoiceCaptureState = {
  status: "idle",
  error: null,
  result: null,
  elapsedSeconds: 0,
};

function isMediaRecorderAvailable(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.MediaRecorder !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia
  );
}

function pickMimeType(): string | undefined {
  if (typeof window === "undefined" || typeof MediaRecorder === "undefined") {
    return undefined;
  }
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  for (const m of candidates) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return undefined;
}

export function useVoiceCapture(
  options: UseVoiceCaptureOptions = {}
): UseVoiceCaptureResult {
  const [state, setState] = useState<UseVoiceCaptureState>(INITIAL);
  // Latest callback in a ref so `stop` stays stable across renders.
  const onTranscriptRef = useRef(options.onTranscript);
  useEffect(() => {
    onTranscriptRef.current = options.onTranscript;
  }, [options.onTranscript]);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);
  const cancelledRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      teardown(recorderRef.current, streamRef.current, timerRef.current);
      recorderRef.current = null;
      streamRef.current = null;
      timerRef.current = null;
    };
  }, []);

  const safeSet = useCallback(
    (next: Partial<UseVoiceCaptureState>) => {
      if (mountedRef.current) setState((prev) => ({ ...prev, ...next }));
    },
    []
  );

  const start = useCallback(async (): Promise<void> => {
    if (!isMediaRecorderAvailable()) {
      safeSet({
        status: "error",
        error: "Voice capture isn't supported in this browser.",
      });
      return;
    }

    safeSet({
      status: "requesting_permission",
      error: null,
      result: null,
      elapsedSeconds: 0,
    });
    cancelledRef.current = false;
    chunksRef.current = [];

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      // Distinguish permission denial from device-missing for clearer UX.
      const name = err instanceof Error ? err.name : "";
      const msg =
        name === "NotAllowedError" || name === "PermissionDeniedError"
          ? "Microphone permission was denied."
          : name === "NotFoundError"
          ? "No microphone was found on this device."
          : "Could not access the microphone.";
      safeSet({ status: "error", error: msg });
      return;
    }

    streamRef.current = stream;
    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(
      stream,
      mimeType ? { mimeType } : undefined
    );
    recorderRef.current = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.start(250); // 250ms timeslice — small chunks, smooth progress
    startTimeRef.current = Date.now();
    timerRef.current = setInterval(() => {
      if (!startTimeRef.current) return;
      const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
      safeSet({ elapsedSeconds: elapsed });
    }, 500);

    safeSet({ status: "recording" });
  }, [safeSet]);

  const stop = useCallback(async (): Promise<void> => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;

    safeSet({ status: "uploading" });

    // Wait for the recorder's final dataavailable + stop events to fire.
    const stopped = new Promise<void>((resolve) => {
      const handler = () => {
        recorder.removeEventListener("stop", handler);
        resolve();
      };
      recorder.addEventListener("stop", handler);
    });
    recorder.stop();
    await stopped;

    // Tear down the stream now that we have the data.
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (cancelledRef.current) {
      // Cancel landed while we were awaiting stop. Discard.
      chunksRef.current = [];
      recorderRef.current = null;
      safeSet({ status: "idle", elapsedSeconds: 0 });
      return;
    }

    const blob = new Blob(chunksRef.current, {
      type: chunksRef.current[0]?.type || "audio/webm",
    });
    chunksRef.current = [];
    recorderRef.current = null;

    if (blob.size === 0) {
      safeSet({
        status: "error",
        error: "No audio was captured — try recording again.",
      });
      return;
    }

    try {
      const result = await runtimeClient.voiceUpload(blob);
      if (!mountedRef.current) return;
      safeSet({ status: "done", result, error: null });
      const transcript =
        typeof result.transcript === "string" ? result.transcript.trim() : "";
      if (result.status === "transcribed" && transcript) {
        onTranscriptRef.current?.(transcript);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      // Backend `detail` messages are client-safe; bare status text isn't useful.
      const message =
        err instanceof RuntimeApiError && err.status > 0 && !/^\d{3}\b/.test(err.message)
          ? err.message
          : err instanceof RuntimeApiError
          ? `Voice upload failed (${err.status}).`
          : "Voice upload failed.";
      safeSet({ status: "error", error: message });
    }
  }, [safeSet]);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    chunksRef.current = [];
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.stop();
      } catch {
        /* ignore — already stopped */
      }
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    recorderRef.current = null;
    safeSet({ status: "idle", elapsedSeconds: 0, error: null });
  }, [safeSet]);

  const reset = useCallback(() => {
    cancel();
    safeSet({ ...INITIAL });
  }, [cancel, safeSet]);

  return { ...state, start, stop, cancel, reset };
}

function teardown(
  recorder: MediaRecorder | null,
  stream: MediaStream | null,
  timer: ReturnType<typeof setInterval> | null
) {
  if (recorder && recorder.state !== "inactive") {
    try {
      recorder.stop();
    } catch {
      /* ignore */
    }
  }
  stream?.getTracks().forEach((t) => t.stop());
  if (timer) clearInterval(timer);
}
