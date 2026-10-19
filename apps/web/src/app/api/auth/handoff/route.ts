/**
 * GET /api/auth/handoff?token=...&verifier=...&next=/today — called inside
 * the native app's WebView after the system-browser sign-in deep-links
 * back (see lib/auth/handoff.ts). Sets the session cookie in the WebView.
 */
import { NextResponse, type NextRequest } from "next/server";

import { redeemHandoff } from "@/lib/auth/handoff";
import { SESSION_COOKIE, encodeSession, safeNext, sessionCookieOptions } from "@/lib/auth/session";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const next = safeNext(params.get("next"));
  const user = await redeemHandoff(params.get("token") ?? "", params.get("verifier") ?? "");
  if (!user) {
    const url = new URL("/login", request.url);
    url.searchParams.set("error", "handoff_failed");
    return NextResponse.redirect(url);
  }
  const res = NextResponse.redirect(new URL(next, request.url));
  res.cookies.set(SESSION_COOKIE, await encodeSession(user), sessionCookieOptions());
  return res;
}
