/**
 * Browser side of the API token (see app/api/token/route.ts): fetched from
 * our own server with the session cookie, cached in memory, refreshed a
 * minute before it expires. Signed-out pages simply get no token.
 */
let cached: { token: string; expiresAt: number } | null = null;
let inflight: Promise<string | null> | null = null;

export async function getApiToken(force = false): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const now = Date.now() / 1000;
  if (!force && cached && cached.expiresAt - now > 60) return cached.token;
  inflight ??= (async () => {
    try {
      const res = await fetch("/api/token", { cache: "no-store", credentials: "same-origin" });
      if (!res.ok) {
        cached = null;
        return null;
      }
      cached = (await res.json()) as { token: string; expiresAt: number };
      return cached.token;
    } catch {
      return null;
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

export function clearApiToken() {
  cached = null;
}
