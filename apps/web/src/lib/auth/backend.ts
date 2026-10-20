/**
 * Server-to-server calls to the FastAPI account endpoints (/v2/auth/*).
 * Carries AUTH_INTERNAL_SECRET, so this must only run on the server.
 */
import type { SessionUser } from "@/lib/auth/session";

export class AuthBackendError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "AuthBackendError";
  }
}

/** AUTH_INTERNAL_SECRET without the spaces, newline or quotes a dashboard paste can add
 * (the API trims the same way). */
export function internalSecret(): string | undefined {
  return process.env.AUTH_INTERNAL_SECRET?.trim().replace(/^['"]|['"]$/g, "").trim() || undefined;
}

export function apiBase(): string {
  const pub = process.env.NEXT_PUBLIC_API_URL;
  // A relative public URL ("/navis-api") is for browsers; servers call the API directly.
  const base = process.env.NAVIS_API_INTERNAL_URL || (pub && /^https?:\/\//.test(pub) ? pub : undefined);
  if (!base && process.env.NODE_ENV === "production") {
    throw new AuthBackendError(503, "Navis isn't configured on this server yet.");
  }
  const url = (base || "http://127.0.0.1:8100").replace(/\/+$/, "");
  // Hosts such as Render pass a private address as "host:port".
  return /^https?:\/\//.test(url) ? url : `http://${url}`;
}

interface BackendUser {
  id: string;
  email: string;
  name?: string | null;
  picture?: string | null;
  session_version?: number;
}

function toSessionUser(u: BackendUser): SessionUser {
  return {
    id: u.id,
    email: u.email,
    name: u.name ?? null,
    picture: u.picture ?? null,
    sessionVersion: typeof u.session_version === "number" ? u.session_version : 0,
  };
}

async function request<T>(
  method: "GET" | "POST" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
  clientIp?: string | null
): Promise<T> {
  const secret = internalSecret();
  if (!secret) throw new AuthBackendError(503, "Sign-in isn't configured on this server yet.");
  const headers: Record<string, string> = { "X-Internal-Auth": secret };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (clientIp) headers["X-Client-IP"] = clientIp.slice(0, 64);
  let response: Response;
  try {
    response = await fetch(`${apiBase()}/v2/auth/${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    throw new AuthBackendError(503, "We can't reach Navis right now. Please try again in a moment.");
  }
  const data = (await response.json().catch(() => ({}))) as T & { detail?: unknown };
  if (!response.ok) {
    const message =
      typeof data.detail === "string" && response.status !== 403
        ? data.detail
        : "Something went wrong. Please try again.";
    throw new AuthBackendError(response.status, message);
  }
  return data;
}

async function userCall(path: string, body: unknown, clientIp?: string | null): Promise<SessionUser> {
  const data = await request<{ user?: BackendUser }>("POST", path, body, clientIp);
  if (!data.user) throw new AuthBackendError(500, "Something went wrong. Please try again.");
  return toSessionUser(data.user);
}

export const authBackend = {
  register: (email: string, password: string, name: string | null, clientIp?: string | null) =>
    userCall("register", { email, password, name }, clientIp),
  login: (email: string, password: string, clientIp?: string | null) =>
    userCall("login", { email, password }, clientIp),
  google: (p: { subject: string; email: string; email_verified: boolean; name?: string | null; picture?: string | null }) =>
    userCall("google", p),
  apple: (p: { subject: string; email: string; email_verified: boolean; name?: string | null }) =>
    userCall("apple", p),
  /** null when the account no longer exists. */
  async getUser(userId: string): Promise<SessionUser | null> {
    try {
      const data = await request<{ user?: BackendUser }>("GET", `users/${encodeURIComponent(userId)}`);
      return data.user ? toSessionUser(data.user) : null;
    } catch (err) {
      if (err instanceof AuthBackendError && err.status === 404) return null;
      throw err;
    }
  },
  deleteAccount: (userId: string) =>
    request<{ deleted: boolean }>("DELETE", `users/${encodeURIComponent(userId)}`),
  signOutEverywhere: async (userId: string) => {
    const data = await request<{ user: BackendUser }>("POST", `users/${encodeURIComponent(userId)}/sign-out-everywhere`, {});
    return toSessionUser(data.user);
  },
  exportAccount: (userId: string) =>
    request<{ account: Record<string, unknown>; data: unknown }>("GET", `users/${encodeURIComponent(userId)}/export`),
};


/** Account data sections the web app syncs (see lib/account/sync.ts). */
export interface AccountData {
  profile: unknown | null;
  saved: unknown | null;
  checklist: unknown | null;
  updated_at: Record<string, number>;
}

async function dataCall(userId: string, method: "GET" | "PUT", body?: unknown): Promise<AccountData> {
  let data: { data?: AccountData };
  try {
    data = await request<{ data?: AccountData }>(method, `users/${encodeURIComponent(userId)}/data`, body);
  } catch (err) {
    if (err instanceof AuthBackendError && err.status === 503) {
      throw new AuthBackendError(503, "Sync isn't available right now.");
    }
    throw err instanceof AuthBackendError ? err : new AuthBackendError(500, "Couldn't sync.");
  }
  if (!data.data) throw new AuthBackendError(500, "Couldn't sync.");
  return data.data;
}

export const accountData = {
  get: (userId: string) => dataCall(userId, "GET"),
  put: (userId: string, sections: Partial<Pick<AccountData, "profile" | "saved" | "checklist">>) =>
    dataCall(userId, "PUT", sections),
};
