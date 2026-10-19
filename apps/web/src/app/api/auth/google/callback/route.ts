/**
 * GET /api/auth/google/callback — finish Google sign-in.
 *
 * Verifies state, exchanges the code (with the PKCE verifier) for tokens,
 * reads the user's profile from Google's userinfo endpoint, creates or
 * links the Navis account, sets the session cookie and redirects on.
 */
import { NextResponse, type NextRequest } from "next/server";

import { AuthBackendError, authBackend } from "@/lib/auth/backend";
import { GOOGLE_STATE_COOKIE, googleConfigured, googleRedirectUri } from "@/lib/auth/google";
import { createHandoff, nativeReturnUrl, validChallenge } from "@/lib/auth/handoff";
import { SESSION_COOKIE, encodeSession, safeNext, sessionCookieOptions } from "@/lib/auth/session";

function fail(request: NextRequest, code: string, next = "/today") {
  const url = new URL("/login", request.url);
  url.searchParams.set("error", code);
  url.searchParams.set("next", next);
  const res = NextResponse.redirect(url);
  res.cookies.delete({ name: GOOGLE_STATE_COOKIE, path: "/api/auth/google" });
  return res;
}

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  let stored: { state?: string; verifier?: string; next?: string; challenge?: string | null } = {};
  try {
    stored = JSON.parse(request.cookies.get(GOOGLE_STATE_COOKIE)?.value ?? "{}");
  } catch {
    stored = {};
  }
  const next = safeNext(stored.next);

  if (!googleConfigured()) return fail(request, "google_unavailable", next);
  if (params.get("error")) return fail(request, "google_cancelled", next);
  const code = params.get("code");
  if (!code || !stored.state || params.get("state") !== stored.state || !stored.verifier) {
    return fail(request, "google_state", next);
  }

  // 1. Code → tokens
  let accessToken: string | undefined;
  try {
    const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: process.env.GOOGLE_CLIENT_ID!,
        client_secret: process.env.GOOGLE_CLIENT_SECRET!,
        redirect_uri: googleRedirectUri(),
        grant_type: "authorization_code",
        code_verifier: stored.verifier,
      }),
      cache: "no-store",
    });
    const tokens = (await tokenRes.json()) as { access_token?: string };
    accessToken = tokenRes.ok ? tokens.access_token : undefined;
  } catch {
    accessToken = undefined;
  }
  if (!accessToken) return fail(request, "google_failed", next);

  // 2. Tokens → profile
  let profile: { sub?: string; email?: string; email_verified?: boolean; name?: string; picture?: string } = {};
  try {
    const infoRes = await fetch("https://openidconnect.googleapis.com/v1/userinfo", {
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    });
    profile = infoRes.ok ? await infoRes.json() : {};
  } catch {
    profile = {};
  }
  if (!profile.sub || !profile.email) return fail(request, "google_failed", next);

  // 3. Profile → Navis account → session
  try {
    const user = await authBackend.google({
      subject: profile.sub,
      email: profile.email,
      email_verified: profile.email_verified === true,
      name: profile.name ?? null,
      picture: profile.picture ?? null,
    });
    const challenge = stored.challenge;
    if (validChallenge(challenge)) {
      const handoff = NextResponse.redirect(nativeReturnUrl(await createHandoff(user, challenge), next));
      handoff.cookies.delete({ name: GOOGLE_STATE_COOKIE, path: "/api/auth/google" });
      return handoff;
    }
    const res = NextResponse.redirect(new URL(next, request.url));
    res.cookies.set(SESSION_COOKIE, await encodeSession(user), sessionCookieOptions());
    res.cookies.delete({ name: GOOGLE_STATE_COOKIE, path: "/api/auth/google" });
    return res;
  } catch (err) {
    const code = err instanceof AuthBackendError && err.status === 403 ? "google_unverified" : "google_failed";
    return fail(request, code, next);
  }
}
