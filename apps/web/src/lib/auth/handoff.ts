/**
 * Native-app sign-in handoff. Google refuses OAuth inside app WebViews, so
 * the iOS/Android shell runs Google/Apple sign-in in the system browser:
 *
 *   1. App makes a random `verifier`, opens the system browser at
 *      /api/auth/google?native=1&challenge=SHA256(verifier)
 *   2. The callback (in the system browser) creates the account, then
 *      redirects to navis://auth/callback?handoff=<signed, 2-minute token>
 *   3. The app catches that deep link and loads
 *      /api/auth/handoff?token=...&verifier=... in its WebView, which checks
 *      the challenge and sets the session cookie there.
 *
 * A token intercepted by another app is useless without the verifier, which
 * never leaves the Navis app. Server-only.
 */
import type { SessionUser } from "@/lib/auth/session";

const enc = new TextEncoder();
const LIFETIME_S = 120;

function b64url(bytes: Uint8Array | ArrayBuffer): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = "";
  for (const b of arr) s += String.fromCharCode(b);
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

function key(): Promise<CryptoKey> {
  keyPromise ??= (async () => {
    const secret = process.env.AUTH_SECRET;
    if (!secret || secret.length < 32) throw new Error("AUTH_SECRET missing");
    const base = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const derived = await crypto.subtle.sign("HMAC", base, enc.encode("navis-native-handoff-v1"));
    return crypto.subtle.importKey("raw", derived, { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
  })();
  return keyPromise;
}

export function nativeScheme(): string {
  return (process.env.NATIVE_APP_SCHEME || "navis").replace(/[^a-z0-9.+-]/gi, "");
}

export function validChallenge(c: string | null | undefined): c is string {
  return typeof c === "string" && /^[A-Za-z0-9_-]{43}$/.test(c);
}

export async function s256(verifier: string): Promise<string> {
  return b64url(await crypto.subtle.digest("SHA-256", enc.encode(verifier)));
}

export async function createHandoff(user: SessionUser, challenge: string): Promise<string> {
  const body = b64url(enc.encode(JSON.stringify({ u: user, c: challenge, exp: Math.floor(Date.now() / 1000) + LIFETIME_S })));
  const sig = await crypto.subtle.sign("HMAC", await key(), enc.encode(body));
  return `${body}.${b64url(sig)}`;
}

export async function redeemHandoff(token: string, verifier: string): Promise<SessionUser | null> {
  const [body, sig] = token.split(".");
  if (!body || !sig || !/^[A-Za-z0-9_-]{43,128}$/.test(verifier)) return null;
  try {
    const ok = await crypto.subtle.verify("HMAC", await key(), fromB64url(sig) as BufferSource, enc.encode(body));
    if (!ok) return null;
    const payload = JSON.parse(new TextDecoder().decode(fromB64url(body))) as { u: SessionUser; c: string; exp: number };
    if (payload.exp * 1000 < Date.now()) return null;
    if ((await s256(verifier)) !== payload.c) return null;
    return payload.u;
  } catch {
    return null;
  }
}

/** Where the system browser sends the user back to the app. */
export function nativeReturnUrl(handoff: string, next: string): string {
  const q = new URLSearchParams({ handoff, next });
  return `${nativeScheme()}://auth/callback?${q.toString()}`;
}
