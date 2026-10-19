/**
 * GET /api/token — a short-lived bearer token for the signed-in user, sent
 * as `Authorization: Bearer ...` on costly API routes (AI, voice, place
 * lookups). Same-origin only; the session cookie never leaves this server.
 */
import { NextResponse } from "next/server";

import { currentUser, mintApiToken } from "@/lib/auth/server";

export async function GET() {
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  try {
    const { token, expiresAt } = await mintApiToken(user.id);
    return NextResponse.json({ token, expiresAt }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "Unavailable" }, { status: 503 });
  }
}
