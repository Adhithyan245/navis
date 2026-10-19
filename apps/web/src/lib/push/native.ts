/**
 * Push notifications inside the native app (Capacitor PushNotifications
 * plugin, reached through the injected window.Capacitor global). On the web
 * every function is a harmless no-op.
 *
 *   enablePush()        ask permission, register, send the token to /api/push/devices
 *   syncPushIfGranted() on launch: refresh the token silently if already allowed
 *   forgetPushDevice()  on sign-out: stop notifications for this account here
 */
import { isNativeApp, nativePlatform } from "@/lib/native";

type Listener = { remove: () => Promise<void> | void };
type PermissionState = "granted" | "denied" | "prompt" | "prompt-with-rationale";

interface PushPlugin {
  checkPermissions(): Promise<{ receive: PermissionState }>;
  requestPermissions(): Promise<{ receive: PermissionState }>;
  register(): Promise<void>;
  createChannel?(c: { id: string; name: string; description?: string; importance?: number; visibility?: number }): Promise<void>;
  addListener(e: "registration", cb: (t: { value: string }) => void): Promise<Listener>;
  addListener(e: "registrationError", cb: (err: { error: string }) => void): Promise<Listener>;
  addListener(
    e: "pushNotificationActionPerformed",
    cb: (a: { notification: { data?: Record<string, unknown> } }) => void
  ): Promise<Listener>;
}

const TOKEN_KEY = "navis_push_token";

function plugin(): PushPlugin | null {
  if (!isNativeApp()) return null;
  const cap = (window as unknown as { Capacitor?: { Plugins?: { PushNotifications?: PushPlugin } } }).Capacitor;
  return cap?.Plugins?.PushNotifications ?? null;
}

export function pushSupported(): boolean {
  return plugin() !== null;
}

function storedToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

async function sendToken(token: string): Promise<boolean> {
  const platform = nativePlatform();
  if (platform === "web") return false;
  const res = await fetch("/api/push/devices", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, platform }),
  }).catch(() => null);
  if (res?.ok) {
    try {
      window.localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage disabled */
    }
  }
  return Boolean(res?.ok);
}

let listenersReady: Promise<void> | null = null;
let pendingRegistration: ((ok: boolean) => void) | null = null;

/** Only same-site paths from a notification are followed. */
function safePath(url: unknown): string | null {
  return typeof url === "string" && url.startsWith("/") && !url.startsWith("//") && !url.includes("\\") ? url : null;
}

function ensureListeners(p: PushPlugin): Promise<void> {
  listenersReady ??= (async () => {
    await p.addListener("registration", async ({ value }) => {
      const ok = await sendToken(value);
      pendingRegistration?.(ok);
      pendingRegistration = null;
    });
    await p.addListener("registrationError", () => {
      pendingRegistration?.(false);
      pendingRegistration = null;
    });
    await p.addListener("pushNotificationActionPerformed", ({ notification }) => {
      const path = safePath(notification.data?.url);
      if (path) window.location.assign(path);
    });
    // Android 8+: separate channels so people can mute reminders but keep alerts.
    await p.createChannel?.({ id: "alerts", name: "Safety alerts", description: "Severe weather and disaster alerts near your city", importance: 5, visibility: 1 });
    await p.createChannel?.({ id: "general", name: "Reminders", description: "Reminders for events you saved", importance: 3, visibility: 1 });
  })();
  return listenersReady;
}

/** Whether the server can deliver to this platform (Firebase / APNs set up). */
export async function pushAvailableHere(): Promise<boolean> {
  const platform = nativePlatform();
  if (platform === "web") return false;
  try {
    const res = await fetch("/api/push/prefs", { cache: "no-store" });
    if (!res.ok) return false;
    const data = (await res.json()) as { available?: Record<string, boolean> };
    return data.available?.[platform] === true;
  } catch {
    return false;
  }
}

export type EnableResult = "enabled" | "denied" | "failed" | "unsupported";

export async function enablePush(): Promise<EnableResult> {
  const p = plugin();
  if (!p || !(await pushAvailableHere())) return "unsupported";
  await ensureListeners(p);
  let perm = (await p.checkPermissions()).receive;
  if (perm !== "granted" && perm !== "denied") perm = (await p.requestPermissions()).receive;
  if (perm !== "granted") return "denied";
  const done = new Promise<boolean>((resolve) => {
    pendingRegistration = resolve;
    setTimeout(() => resolve(false), 15_000);
  });
  await p.register();
  return (await done) ? "enabled" : "failed";
}

export async function syncPushIfGranted(): Promise<void> {
  const p = plugin();
  if (!p || !(await pushAvailableHere())) return;
  await ensureListeners(p);
  if ((await p.checkPermissions()).receive === "granted") await p.register();
}

export async function forgetPushDevice(): Promise<void> {
  const token = typeof window === "undefined" ? null : storedToken();
  if (!token) return;
  await fetch("/api/push/devices", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
    keepalive: true,
  }).catch(() => undefined);
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage disabled */
  }
}
