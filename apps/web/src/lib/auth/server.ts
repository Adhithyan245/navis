/**
 * Server-only auth helpers shared by layouts, route handlers and actions.
 *
 *   currentUser()   session cookie → user, re-checked against the account
 *                   (deleted accounts and "sign out everywhere" take effect
 *                   within a minute)
 *   clientIp()      visitor IP for sign-up / login throttles
 *   sameOrigin()    CSRF check for state-changing route handlers
 *   mintApiToken()  short-lived bearer token for costly API routes
 */
import { cookies, headers } from "next/headers";
import type { NextRequest } from "next/server";

import { AuthBackendError, authBackend } from "@/lib/auth/backend";
import { hostedAppUrl } from "@/lib/auth/google";
import { SESSION_COOKIE, decodeSession, type SessionUser } from "@/lib/auth/session";

const CHECK_TTL_MS = 60_000;
const MAX_CHECKS = 5000;
// userId → { version (null = account gone), checkedAt }
const checks = new Map<string, { version: number | null; at: number }>();

async function liveVersion(userId: string): Promise<number | null | undefined> {
  const hit = checks.get(userId);
  if (hit && Date.now() - hit.at < CHECK_TTL_MS) return hit.version;
  try {
    const user = await authBackend.getUser(userId);
    const version = user ? user.sessionVersion ?? 0 : null;
    checks.set(userId, { version, at: Date.now() });
    if (checks.size > MAX_CHECKS) checks.delete(checks.keys().next().value as string);
    return version;
  } catch (err) {
    // Backend unreachable: don't sign everyone out; the cookie is still signed.
    if (err instanceof AuthBackendError) return undefined;
    return undefined;
  }
}

export function forgetSessionCheck(userId: string) {
  checks.delete(userId);
}

/** The signed-in user, or null (no/invalid cookie, account deleted, or revoked). */
export async function currentUser(): Promise<SessionUser | null> {
  const user = await decodeSession((await cookies()).get(SESSION_COOKIE)?.value);
  if (!user) return null;
  const version = await liveVersion(user.id);
  if (version === null) return null; // account deleted
  if (typeof version === "number" && (user.sessionVersion ?? 0) < version) return null; // revoked
  return user;
}

export async function clientIp(): Promise<string | null> {
  const h = await headers();
  const forwarded = h.get("x-forwarded-for")?.split(",")[0]?.trim();
  return forwarded || h.get("x-real-ip") || null;
}

function appOrigin(): string | null {
  const url = hostedAppUrl();
  try {
    return url ? new URL(url).origin : null;
  } catch {
    return null;
  }
}

/** The public origin the browser used. Behind a host's proxy, nextUrl is the
 * internal address (e.g. http://localhost:10000), so read the forwarded host. */
function requestOrigin(request: NextRequest): string | null {
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  if (!host) return null;
  const proto = (request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol.replace(":", "")).split(",")[0].trim();
  return `${proto}://${host.split(",")[0].trim()}`;
}

/** True when a state-changing request comes from our own pages. */
export function sameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) {
    // Browsers always send Origin on cross-site POST/PUT/DELETE; a missing
    // one means same-origin navigation or a non-browser client with no cookie.
    return request.headers.get("sec-fetch-site") !== "cross-site";
  }
  // Cross-site pages can't forge Host / X-Forwarded-Host on a browser request
  // (forbidden or preflighted headers), so matching them is safe for CSRF.
  const allowed = new Set([request.nextUrl.origin]);
  for (const o of [appOrigin(), requestOrigin(request)]) if (o) allowed.add(o);
  return allowed.has(origin);
}

// ── API tokens (verified by apps/api/core/api_token.py) ────────────────────

const enc = new TextEncoder();
let tokenKey: Promise<CryptoKey> | null = null;

async function hmacKey(raw: BufferSource): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
}

function apiTokenKey(): Promise<CryptoKey> {
  tokenKey ??= (async () => {
    const explicit = process.env.API_TOKEN_SECRET;
    if (explicit) return hmacKey(enc.encode(explicit));
    const internal = process.env.AUTH_INTERNAL_SECRET;
    if (!internal) throw new Error("AUTH_INTERNAL_SECRET is not set");
    const derived = await crypto.subtle.sign("HMAC", await hmacKey(enc.encode(internal)), enc.encode("navis-api-token-v1"));
    return hmacKey(derived);
  })();
  return tokenKey;
}

export const API_TOKEN_LIFETIME_S = 30 * 60;

export async function mintApiToken(userId: string): Promise<{ token: string; expiresAt: number }> {
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(userId)) throw new Error("bad user id");
  const expiresAt = Math.floor(Date.now() / 1000) + API_TOKEN_LIFETIME_S;
  const body = `v1.${userId}.${expiresAt}`;
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", await apiTokenKey(), enc.encode(body)));
  const hex = Array.from(sig, (b) => b.toString(16).padStart(2, "0")).join("");
  return { token: `${body}.${hex}`, expiresAt };
}
