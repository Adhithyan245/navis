/**
 * Bridge to the Capacitor shell (apps/mobile). The native app loads this
 * site in a WebView and injects `window.Capacitor`; on the plain web all of
 * this is a no-op. Plugins are reached through the injected global so the
 * web bundle doesn't need the Capacitor packages.
 */
type Listener = { remove: () => Promise<void> | void };

interface CapacitorGlobal {
  isNativePlatform?: () => boolean;
  getPlatform?: () => string;
  Plugins?: {
    Browser?: { open: (o: { url: string; presentationStyle?: string }) => Promise<void>; close?: () => Promise<void> };
    App?: {
      addListener(event: "appUrlOpen", cb: (e: { url: string }) => void): Promise<Listener> | Listener;
      addListener(event: "backButton", cb: (e: { canGoBack: boolean }) => void): Promise<Listener> | Listener;
      exitApp?: () => Promise<void>;
    };
  };
}

function cap(): CapacitorGlobal | null {
  if (typeof window === "undefined") return null;
  return ((window as unknown as { Capacitor?: CapacitorGlobal }).Capacitor ?? null);
}

export function isNativeApp(): boolean {
  return Boolean(cap()?.isNativePlatform?.());
}

export function nativePlatform(): "ios" | "android" | "web" {
  const p = cap()?.getPlatform?.();
  return p === "ios" || p === "android" ? p : "web";
}

function b64url(bytes: Uint8Array | ArrayBuffer): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = "";
  for (const b of arr) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * Google/Apple sign-in from the native app: run it in the system browser
 * (Google blocks WebViews), then finish inside the WebView via the signed
 * handoff (see lib/auth/handoff.ts).
 */
export async function nativeOAuth(provider: "google" | "apple", next: string): Promise<void> {
  const c = cap();
  const browser = c?.Plugins?.Browser;
  const app = c?.Plugins?.App;
  if (!browser || !app) {
    window.location.assign(`/api/auth/${provider}?next=${encodeURIComponent(next)}`);
    return;
  }
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(48)));
  const challenge = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));

  const listener = await app.addListener("appUrlOpen", async ({ url }) => {
    let parsed: URL;
    try {
      parsed = new URL(url);
    } catch {
      return;
    }
    const handoff = parsed.searchParams.get("handoff");
    if (!handoff) return;
    await listener.remove();
    await browser.close?.().catch(() => undefined);
    const q = new URLSearchParams({ token: handoff, verifier, next: parsed.searchParams.get("next") || next });
    window.location.assign(`/api/auth/handoff?${q.toString()}`);
  });

  const start = new URL(`/api/auth/${provider}`, window.location.origin);
  start.searchParams.set("next", next);
  start.searchParams.set("native", "1");
  start.searchParams.set("challenge", challenge);
  await browser.open({ url: start.toString(), presentationStyle: "popover" });
}

/**
 * Native niceties when running inside the app: the Android back button
 * walks the in-app history (and exits from the first screen), like any
 * native app. Returns a cleanup function.
 */
export function initNativeShell(): () => void {
  const app = cap()?.Plugins?.App;
  if (!isNativeApp() || !app) return () => undefined;
  let listener: Listener | null = null;
  void Promise.resolve(
    app.addListener("backButton", ({ canGoBack }) => {
      if (canGoBack && window.history.length > 1) window.history.back();
      else void app.exitApp?.();
    })
  ).then((l) => {
    listener = l;
  });
  document.documentElement.classList.add("native-app");
  return () => {
    void listener?.remove();
  };
}
