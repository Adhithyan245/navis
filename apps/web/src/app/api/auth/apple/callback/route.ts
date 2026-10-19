/**
 * POST /api/auth/apple/callback — Apple's form_post response. Verifies
 * state, exchanges the code, verifies the id_token, creates or links the
 * Navis account, then signs in (or hands off to the native app).
 */
import { NextResponse, type NextRequest } from "next/server";

import { APPLE_STATE_COOKIE, appleConfigured, appleExchange } from "@/lib/auth/apple";
import { AuthBackendError, authBackend } from "@/lib/auth/backend";
import { createHandoff, nativeReturnUrl, validChallenge } from "@/lib/auth/handoff";
import { SESSION_COOKIE, encodeSession, safeNext, sessionCookieOptions } from "@/lib/auth/session";

function fail(request: NextRequest, code: string, next = "/today") {
  const url = new URL("/login", request.url);
  url.searchParams.set("error", code);
  url.searchParams.set("next", next);
  const res = NextResponse.redirect(url, 303);
  res.cookies.delete({ name: APPLE_STATE_COOKIE, path: "/api/auth/apple" });
  return res;
}

export async function POST(request: NextRequest) {
  let stored: { state?: string; nonce?: string; next?: string; challenge?: string | null } = {};
  try {
    stored = JSON.parse(request.cookies.get(APPLE_STATE_COOKIE)?.value ?? "{}");
  } catch {
    stored = {};
  }
  const next = safeNext(stored.next);
  if (!appleConfigured()) return fail(request, "apple_unavailable", next);

  const form = await request.formData().catch(() => null);
  if (!form) return fail(request, "apple_failed", next);
  if (form.get("error")) return fail(request, "apple_cancelled", next);
  const code = form.get("code");
  const state = form.get("state");
  if (typeof code !== "string" || !stored.state || state !== stored.state || !stored.nonce) {
    return fail(request, "apple_state", next);
  }

  let claims;
  try {
    claims = await appleExchange(code, stored.nonce);
  } catch {
    return fail(request, "apple_failed", next);
  }
  if (!claims.sub || !claims.email) return fail(request, "apple_failed", next);

  // Apple sends the name only on the very first sign-in, outside the token.
  let name: string | null = null;
  try {
    const user = JSON.parse(String(form.get("user") ?? "null")) as { name?: { firstName?: string; lastName?: string } } | null;
    name = [user?.name?.firstName, user?.name?.lastName].filter(Boolean).join(" ").slice(0, 80) || null;
  } catch {
    name = null;
  }

  try {
    const user = await authBackend.apple({
      subject: claims.sub,
      email: claims.email,
      email_verified: claims.email_verified === true || claims.email_verified === "true",
      name,
    });
    const challenge = stored.challenge;
    if (validChallenge(challenge)) {
      const res = NextResponse.redirect(nativeReturnUrl(await createHandoff(user, challenge), next), 303);
      res.cookies.delete({ name: APPLE_STATE_COOKIE, path: "/api/auth/apple" });
      return res;
    }
    const res = NextResponse.redirect(new URL(next, request.url), 303);
    res.cookies.set(SESSION_COOKIE, await encodeSession(user), sessionCookieOptions());
    res.cookies.delete({ name: APPLE_STATE_COOKIE, path: "/api/auth/apple" });
    return res;
  } catch (err) {
    const c = err instanceof AuthBackendError && err.status === 403 ? "apple_unverified" : "apple_failed";
    return fail(request, c, next);
  }
}
