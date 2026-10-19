/**
 * DELETE /api/account — permanently delete the signed-in account and all
 * synced data (profile, saved items, checklist), then sign out. Required
 * by the App Store (5.1.1(v)) and Google Play account-deletion policies.
 * Body: { confirm: "DELETE" }.
 */
import { NextResponse, type NextRequest } from "next/server";

import { AuthBackendError, authBackend } from "@/lib/auth/backend";
import { currentUser, forgetSessionCheck, sameOrigin } from "@/lib/auth/server";
import { SESSION_COOKIE } from "@/lib/auth/session";

export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  const body = (await request.json().catch(() => ({}))) as { confirm?: string };
  if (body.confirm !== "DELETE") {
    return NextResponse.json({ error: "Type DELETE to confirm." }, { status: 422 });
  }
  try {
    await authBackend.deleteAccount(user.id);
  } catch (err) {
    if (!(err instanceof AuthBackendError && err.status === 404)) {
      return NextResponse.json({ error: "We couldn't delete your account right now. Please try again." }, { status: 503 });
    }
  }
  forgetSessionCheck(user.id);
  const res = NextResponse.json({ deleted: true });
  res.cookies.delete(SESSION_COOKIE);
  return res;
}
