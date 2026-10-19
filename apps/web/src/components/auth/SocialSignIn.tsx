"use client";
/**
 * "Continue with Apple / Google". On the web these are plain links to the
 * OAuth routes; inside the native app they open the system browser and
 * hand the session back (lib/native.ts).
 */
import { isNativeApp, nativeOAuth } from "@/lib/native";

const BASE =
  "flex h-11 items-center justify-center gap-3 rounded-xl border text-sm font-medium shadow-sm transition-colors";

function onNative(provider: "google" | "apple", next: string) {
  return (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (!isNativeApp()) return;
    e.preventDefault();
    void nativeOAuth(provider, next);
  };
}

export function SocialSignIn({ next, googleEnabled, appleEnabled }: { next: string; googleEnabled: boolean; appleEnabled: boolean }) {
  const q = `?next=${encodeURIComponent(next)}`;
  return (
    <div className="flex flex-col gap-2.5">
      {appleEnabled && (
        <a
          href={`/api/auth/apple${q}`}
          onClick={onNative("apple", next)}
          className={`${BASE} border-zinc-900 bg-zinc-900 text-white hover:bg-zinc-800 dark:border-white dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-100`}
        >
          <AppleMark />
          Continue with Apple
        </a>
      )}
      <a
        href={googleEnabled ? `/api/auth/google${q}` : undefined}
        onClick={googleEnabled ? onNative("google", next) : undefined}
        aria-disabled={!googleEnabled}
        title={googleEnabled ? undefined : "Google sign-in isn't set up on this server yet"}
        className={
          `${BASE} border-zinc-200 bg-white text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 ` +
          (googleEnabled ? "hover:bg-zinc-50 dark:hover:bg-zinc-800" : "cursor-not-allowed opacity-50")
        }
      >
        <GoogleMark />
        Continue with Google
      </a>
    </div>
  );
}

function AppleMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-[18px]" aria-hidden fill="currentColor">
      <path d="M16.37 12.6c-.02-2.2 1.8-3.26 1.88-3.31-1.03-1.5-2.62-1.7-3.18-1.73-1.35-.14-2.64.8-3.33.8-.69 0-1.74-.78-2.86-.76-1.47.02-2.83.86-3.59 2.17-1.53 2.65-.39 6.58 1.1 8.73.73 1.05 1.6 2.24 2.73 2.2 1.1-.05 1.51-.71 2.84-.71 1.32 0 1.7.71 2.86.69 1.18-.02 1.93-1.07 2.65-2.13.84-1.22 1.18-2.4 1.2-2.46-.03-.01-2.3-.88-2.3-3.5ZM14.2 6.13c.6-.73 1.01-1.75.9-2.76-.87.04-1.92.58-2.54 1.31-.56.65-1.05 1.69-.92 2.68.97.08 1.96-.49 2.56-1.23Z" />
    </svg>
  );
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-[18px]" aria-hidden>
      <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.24 1.4-1.7 4.1-5.5 4.1-3.3 0-6-2.74-6-6.1S8.7 6 12 6c1.88 0 3.14.8 3.86 1.49l2.63-2.53C16.8 3.4 14.6 2.4 12 2.4 6.7 2.4 2.4 6.7 2.4 12s4.3 9.6 9.6 9.6c5.54 0 9.2-3.9 9.2-9.38 0-.63-.07-1.11-.16-1.6H12Z" />
    </svg>
  );
}
