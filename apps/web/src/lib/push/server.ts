/**
 * Server-to-server calls to the API's push endpoints (/v2/push/*). Carries
 * AUTH_INTERNAL_SECRET, so this must only run on the server.
 */
import { AuthBackendError, apiBase } from "@/lib/auth/backend";

export interface PushPrefs {
  safety_alerts: boolean;
  event_reminders: boolean;
  devices: number;
}

async function call<T>(method: "GET" | "PUT" | "POST" | "DELETE", path: string, body?: unknown): Promise<T> {
  const secret = process.env.AUTH_INTERNAL_SECRET;
  if (!secret) throw new AuthBackendError(503, "Notifications aren't configured on this server yet.");
  let response: Response;
  try {
    response = await fetch(`${apiBase()}/v2/push/${path}`, {
      method,
      headers: { "X-Internal-Auth": secret, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    throw new AuthBackendError(503, "We can't reach Navis right now.");
  }
  const data = (await response.json().catch(() => ({}))) as T & { detail?: unknown };
  if (!response.ok) {
    const message = typeof data.detail === "string" && response.status !== 403 ? data.detail : "Something went wrong.";
    throw new AuthBackendError(response.status, message);
  }
  return data;
}

const u = (userId: string) => `users/${encodeURIComponent(userId)}`;

export const pushBackend = {
  registerDevice: (userId: string, token: string, platform: "android" | "ios") =>
    call<{ prefs: PushPrefs }>("PUT", `${u(userId)}/devices`, { token, platform }),
  unregisterDevice: (userId: string, token: string) => call<{ ok: boolean }>("DELETE", `${u(userId)}/devices`, { token }),
  getPrefs: (userId: string) =>
    call<{ prefs: PushPrefs; available?: { android: boolean; ios: boolean } }>("GET", `${u(userId)}/prefs`),
  setPrefs: (userId: string, changes: Partial<Omit<PushPrefs, "devices">>) =>
    call<{ prefs: PushPrefs }>("PUT", `${u(userId)}/prefs`, changes),
  test: (userId: string) => call<{ result: Record<string, number> }>("POST", `${u(userId)}/test`, {}),
};
