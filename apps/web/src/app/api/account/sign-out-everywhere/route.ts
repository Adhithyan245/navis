/**
 * POST /api/account/sign-out-everywhere — invalidate every session for this
 * account (other phones, browsers), keeping this one signed in.
 */
import { NextResponse, type NextRequest } from "next/server";

import { authBackend } from "@/lib/auth/backend";
import { currentUser, forgetSessionCheck, sameOrigin } from "@/lib/auth/server";
import { SESSION_COOKIE, encodeSession, sessionCookieOptions } from "@/lib/auth/session";

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  try {
    const updated = await authBackend.signOutEverywhere(user.id);
    forgetSessionCheck(user.id);
    const res = NextResponse.json({ ok: true });
    res.cookies.set(SESSION_COOKIE, await encodeSession({ ...user, sessionVersion: updated.sessionVersion }), sessionCookieOptions());
    return res;
  } catch {
    return NextResponse.json({ error: "That didn't work. Please try again." }, { status: 503 });
  }
}
