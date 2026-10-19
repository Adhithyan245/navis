/**
 * GET /api/auth/apple?next=/events[&native=1&challenge=...] — start Sign in
 * with Apple. Apple answers with a cross-site form POST, so the state
 * cookie must be SameSite=None (and therefore Secure).
 */
import { NextResponse, type NextRequest } from "next/server";

import { APPLE_STATE_COOKIE, appleAuthorizeUrl, appleConfigured } from "@/lib/auth/apple";
import { randomToken } from "@/lib/auth/google";
import { validChallenge } from "@/lib/auth/handoff";
import { safeNext } from "@/lib/auth/session";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const next = safeNext(params.get("next"));
  const raw = params.get("challenge");
  const challenge = params.get("native") === "1" && validChallenge(raw) ? raw : null;
  if (!appleConfigured()) {
    const url = new URL("/login", request.url);
    url.searchParams.set("error", "apple_unavailable");
    url.searchParams.set("next", next);
    return NextResponse.redirect(url);
  }
  const state = randomToken();
  const nonce = randomToken();
  const response = NextResponse.redirect(appleAuthorizeUrl(state, nonce));
  response.cookies.set(APPLE_STATE_COOKIE, JSON.stringify({ state, nonce, next, challenge }), {
    httpOnly: true,
    secure: true,
    sameSite: "none",
    path: "/api/auth/apple",
    maxAge: 600,
  });
  return response;
}
