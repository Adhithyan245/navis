"use client";
/**
 * VoiceMicButton — real microphone capture button.
 *
 * Click to start recording, click again to stop and transcribe. Status
 * reflects actual permission/recording/upload state from useVoiceCapture.
 * The transcript is shown and handed to `onTranscript` (the query box runs
 * it); a clip with no speech shows the backend's message instead.
 *
 * No simulateVoiceQuery() — every state shown corresponds to a real event.
 */
import { Loader2, Mic, MicOff, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useVoiceCapture } from "@/hooks/useVoiceCapture";
import { cn } from "@/lib/utils";

interface VoiceMicButtonProps {
  /** Optional className for the outer wrapper. */
  className?: string;
  /** Receives the transcript after a successful transcription. */
  onTranscript?: (text: string) => void;
}

export function VoiceMicButton({ className, onTranscript }: VoiceMicButtonProps) {
  const {
    status,
    elapsedSeconds,
    error,
    result,
    start,
    stop,
    cancel,
    reset,
  } = useVoiceCapture({ onTranscript });

  const isActive =
    status === "requesting_permission" ||
    status === "recording" ||
    status === "uploading";

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-center gap-2">
        {!isActive && status !== "done" && status !== "error" && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void start()}
            aria-label="Start voice recording"
          >
            <Mic />
            Voice
          </Button>
        )}

        {status === "requesting_permission" && (
          <Button variant="outline" size="sm" disabled>
            <Loader2 className="animate-spin" />
            Requesting mic…
          </Button>
        )}

        {status === "recording" && (
          <>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => void stop()}
              aria-label="Stop and upload"
            >
              <MicOff />
              Stop · {formatElapsed(elapsedSeconds)}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={cancel}
              aria-label="Discard recording"
            >
              <X />
            </Button>
          </>
        )}

        {status === "uploading" && (
          <Button variant="outline" size="sm" disabled>
            <Loader2 className="animate-spin" />
            Transcribing…
          </Button>
        )}

        {status === "done" && (
          <Button variant="outline" size="sm" onClick={reset}>
            <Mic />
            Record again
          </Button>
        )}

        {status === "error" && (
          <Button variant="outline" size="sm" onClick={reset}>
            <Mic />
            Try again
          </Button>
        )}
      </div>

      {/* Result + error surfaces */}
      {status === "done" && result && (
        result.status === "transcribed" && result.transcript ? (
          <p
            role="status"
            className="max-w-xs rounded-lg border border-indigo-200/70 bg-indigo-50/80 px-3 py-2 text-xs text-indigo-900 dark:border-indigo-400/20 dark:bg-indigo-500/10 dark:text-indigo-200"
          >
            Heard: “{result.transcript}”
          </p>
        ) : (
          <p
            role="status"
            className="max-w-xs rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200"
          >
            {result.message}
          </p>
        )
      )}

      {status === "error" && error && (
        <div
          role="alert"
          className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900 dark:border-rose-900/40 dark:bg-rose-950/30 dark:text-rose-200"
        >
          {error}
        </div>
      )}
    </div>
  );
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
