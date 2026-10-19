/**
 * Sign in with Apple (web flow, also used from the native apps via the
 * system browser). Server-only.
 *
 * Env (from the Apple Developer account):
 *   APPLE_CLIENT_ID     Services ID, e.g. com.navis.web
 *   APPLE_TEAM_ID       10-character team id
 *   APPLE_KEY_ID        id of the "Sign in with Apple" key
 *   APPLE_PRIVATE_KEY   contents of the .p8 key (PEM; "\n" escapes allowed)
 *
 * Flow: /api/auth/apple → Apple (response_mode=form_post) → POST
 * /api/auth/apple/callback. The id_token from Apple's token endpoint is
 * verified (RS256 against Apple's JWKS, issuer, audience, expiry, nonce).
 */
import { appUrl } from "@/lib/auth/google";

export const APPLE_STATE_COOKIE = "navis_apple";
const ISSUER = "https://appleid.apple.com";

export function appleConfigured(): boolean {
  return Boolean(
    process.env.APPLE_CLIENT_ID && process.env.APPLE_TEAM_ID && process.env.APPLE_KEY_ID && process.env.APPLE_PRIVATE_KEY
  );
}

export function appleRedirectUri(): string {
  return `${appUrl()}/api/auth/apple/callback`;
}

const enc = new TextEncoder();

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

function pemToDer(pem: string): Uint8Array {
  const body = pem.replace(/\\n/g, "\n").replace(/-----[^-]+-----/g, "").replace(/\s+/g, "");
  const bin = atob(body);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** ES256 client secret JWT for Apple's token endpoint (valid 5 minutes). */
async function clientSecret(): Promise<string> {
  const key = await crypto.subtle.importKey(
    "pkcs8",
    pemToDer(process.env.APPLE_PRIVATE_KEY!) as BufferSource,
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["sign"]
  );
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(enc.encode(JSON.stringify({ alg: "ES256", kid: process.env.APPLE_KEY_ID })));
  const payload = b64url(
    enc.encode(
      JSON.stringify({ iss: process.env.APPLE_TEAM_ID, iat: now, exp: now + 300, aud: ISSUER, sub: process.env.APPLE_CLIENT_ID })
    )
  );
  // WebCrypto ECDSA signatures are already the raw r||s form JWS expects.
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, enc.encode(`${header}.${payload}`));
  return `${header}.${payload}.${b64url(sig)}`;
}

interface AppleClaims {
  iss: string;
  aud: string | string[];
  exp: number;
  sub: string;
  nonce?: string;
  email?: string;
  email_verified?: boolean | string;
}

let jwksCache: { keys: Array<JsonWebKey & { kid?: string }>; at: number } | null = null;

async function appleKeys(): Promise<Array<JsonWebKey & { kid?: string }>> {
  if (jwksCache && Date.now() - jwksCache.at < 60 * 60 * 1000) return jwksCache.keys;
  const res = await fetch(`${ISSUER}/auth/keys`, { cache: "no-store", signal: AbortSignal.timeout(10_000) });
  if (!res.ok) throw new Error("apple jwks unavailable");
  const data = (await res.json()) as { keys: Array<JsonWebKey & { kid?: string }> };
  jwksCache = { keys: data.keys, at: Date.now() };
  return data.keys;
}

async function verifyIdToken(idToken: string, nonce: string): Promise<AppleClaims> {
  const [h, p, s] = idToken.split(".");
  if (!h || !p || !s) throw new Error("malformed id_token");
  const header = JSON.parse(new TextDecoder().decode(fromB64url(h))) as { alg?: string; kid?: string };
  if (header.alg !== "RS256") throw new Error("unexpected alg");
  const jwk = (await appleKeys()).find((k) => k.kid === header.kid);
  if (!jwk) throw new Error("unknown key");
  const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, fromB64url(s) as BufferSource, enc.encode(`${h}.${p}`));
  if (!ok) throw new Error("bad signature");
  const claims = JSON.parse(new TextDecoder().decode(fromB64url(p))) as AppleClaims;
  const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (claims.iss !== ISSUER || !aud.includes(process.env.APPLE_CLIENT_ID!)) throw new Error("bad issuer/audience");
  if (claims.exp * 1000 < Date.now()) throw new Error("expired");
  if (!claims.nonce || claims.nonce !== nonce) throw new Error("bad nonce");
  return claims;
}

export async function appleExchange(code: string, nonce: string): Promise<AppleClaims> {
  const res = await fetch(`${ISSUER}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: process.env.APPLE_CLIENT_ID!,
      client_secret: await clientSecret(),
      code,
      grant_type: "authorization_code",
      redirect_uri: appleRedirectUri(),
    }),
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
  const tokens = (await res.json().catch(() => ({}))) as { id_token?: string };
  if (!res.ok || !tokens.id_token) throw new Error("apple token exchange failed");
  return verifyIdToken(tokens.id_token, nonce);
}

export function appleAuthorizeUrl(state: string, nonce: string): URL {
  const url = new URL(`${ISSUER}/auth/authorize`);
  url.searchParams.set("client_id", process.env.APPLE_CLIENT_ID!);
  url.searchParams.set("redirect_uri", appleRedirectUri());
  url.searchParams.set("response_type", "code");
  url.searchParams.set("response_mode", "form_post");
  url.searchParams.set("scope", "name email");
  url.searchParams.set("state", state);
  url.searchParams.set("nonce", nonce);
  return url;
}
