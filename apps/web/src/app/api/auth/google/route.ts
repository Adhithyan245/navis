/**
 * GET /api/auth/google?next=/events[&native=1&challenge=...] — start Google sign-in.
 * Stores state + PKCE verifier + next in a short-lived httpOnly cookie and
 * redirects to Google's consent screen.
 */
import { NextResponse, type NextRequest } from "next/server";

import {
  GOOGLE_STATE_COOKIE,
  googleConfigured,
  googleRedirectUri,
  pkceChallenge,
  randomToken,
} from "@/lib/auth/google";
import { validChallenge } from "@/lib/auth/handoff";
import { safeNext } from "@/lib/auth/session";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const next = safeNext(params.get("next"));
  // From the native app (system browser): hand the session back via deep link.
  const raw = params.get("challenge");
  const challenge = params.get("native") === "1" && validChallenge(raw) ? raw : null;
  if (!googleConfigured()) {
    const url = new URL("/login", request.url);
    url.searchParams.set("error", "google_unavailable");
    url.searchParams.set("next", next);
    return NextResponse.redirect(url);
  }

  const state = randomToken();
  const verifier = randomToken(48);
  const auth = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  auth.searchParams.set("client_id", process.env.GOOGLE_CLIENT_ID!);
  auth.searchParams.set("redirect_uri", googleRedirectUri());
  auth.searchParams.set("response_type", "code");
  auth.searchParams.set("scope", "openid email profile");
  auth.searchParams.set("state", state);
  auth.searchParams.set("code_challenge", await pkceChallenge(verifier));
  auth.searchParams.set("code_challenge_method", "S256");
  auth.searchParams.set("prompt", "select_account");

  const response = NextResponse.redirect(auth);
  response.cookies.set(GOOGLE_STATE_COOKIE, JSON.stringify({ state, verifier, next, challenge }), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/api/auth/google",
    maxAge: 600,
  });
  return response;
}
