/**
 * Stateless sessions: a signed, httpOnly cookie holding the user's id,
 * email, name and picture plus an expiry.
 *
 * Format: base64url(JSON payload) + "." + base64url(HMAC-SHA256). Signed
 * with AUTH_SECRET (server-only env). Uses Web Crypto so the same code runs
 * in route handlers, server components and proxy.ts.
 *
 * Server-side only: never import from a "use client" module.
 */

export const SESSION_COOKIE = "navis_session";
export const SESSION_MAX_AGE_S = 60 * 60 * 24 * 14; // 14 days

export interface SessionUser {
  id: string;
  email: string;
  name: string | null;
  picture: string | null;
  /** Account's session_version when signed in; older cookies are revoked. */
  sessionVersion?: number;
}

interface SessionPayload extends SessionUser {
  exp: number; // epoch seconds
}

const encoder = new TextEncoder();

function b64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromB64url(s: string): Uint8Array {
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/") + pad);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

let keyPromise: Promise<CryptoKey> | null = null;

function signingKey(): Promise<CryptoKey> {
  const secret = process.env.AUTH_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error("AUTH_SECRET is missing or too short (need 32+ characters) in apps/web/.env.local");
  }
  keyPromise ??= crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
  return keyPromise;
}

export async function encodeSession(user: SessionUser): Promise<string> {
  const payload: SessionPayload = {
    id: user.id,
    email: user.email,
    name: user.name,
    picture: user.picture,
    sessionVersion: user.sessionVersion ?? 0,
    exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE_S,
  };
  const body = b64url(encoder.encode(JSON.stringify(payload)));
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", await signingKey(), encoder.encode(body)));
  return `${body}.${b64url(sig)}`;
}

/** Returns the user for a valid, unexpired token; null otherwise. Never throws. */
export async function decodeSession(token: string | undefined | null): Promise<SessionUser | null> {
  if (!token) return null;
  const dot = token.indexOf(".");
  if (dot <= 0) return null;
  const body = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  try {
    const ok = await crypto.subtle.verify(
      "HMAC",
      await signingKey(),
      fromB64url(sig) as BufferSource,
      encoder.encode(body)
    );
    if (!ok) return null;
    const payload = JSON.parse(new TextDecoder().decode(fromB64url(body))) as SessionPayload;
    if (typeof payload.exp !== "number" || payload.exp * 1000 < Date.now()) return null;
    if (typeof payload.id !== "string" || typeof payload.email !== "string") return null;
    return {
      id: payload.id,
      email: payload.email,
      name: payload.name ?? null,
      picture: payload.picture ?? null,
      sessionVersion: typeof payload.sessionVersion === "number" ? payload.sessionVersion : 0,
    };
  } catch {
    return null;
  }
}

export function sessionCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: SESSION_MAX_AGE_S,
  };
}

/**
 * Only allow same-site relative redirect targets ("/events"), never
 * "//evil", "/\\evil" or "/<TAB>/evil" (browsers strip tabs/newlines, which
 * turns that into "//evil"). Resolve against a dummy origin and require
 * that the origin didn't change.
 */
export function safeNext(next: string | null | undefined, fallback = "/today"): string {
  if (!next || next.length > 512 || !next.startsWith("/")) return fallback;
  if (/[\u0000-\u001f\u007f\\]/.test(next)) return fallback;
  let resolved: URL;
  try {
    resolved = new URL(next, "https://navis.invalid");
  } catch {
    return fallback;
  }
  if (resolved.origin !== "https://navis.invalid") return fallback;
  const path = `${resolved.pathname}${resolved.search}${resolved.hash}`;
  if (path.startsWith("//") || path.startsWith("/login") || path.startsWith("/signup") || path.startsWith("/api/")) {
    return fallback;
  }
  return path;
}
