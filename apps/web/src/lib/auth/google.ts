/** Google OAuth 2.0 / OpenID Connect helpers (authorization-code + PKCE). */

export const GOOGLE_STATE_COOKIE = "navis_oauth";

export function googleConfigured(): boolean {
  return Boolean(process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET);
}

export function appUrl(): string {
  // RENDER_EXTERNAL_URL is set automatically on Render; a custom domain goes in APP_URL.
  return (process.env.APP_URL || process.env.RENDER_EXTERNAL_URL || "http://localhost:3000").replace(/\/+$/, "");
}

export function googleRedirectUri(): string {
  return `${appUrl()}/api/auth/google/callback`;
}

function b64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function randomToken(bytes = 32): string {
  return b64url(crypto.getRandomValues(new Uint8Array(bytes)));
}

export async function pkceChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return b64url(new Uint8Array(digest));
}
