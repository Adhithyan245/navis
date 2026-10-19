/**
 * /api/me/data — the signed-in user's synced profile, saved items and
 * checklist progress.
 *
 *   GET  → { data: { profile, saved, checklist, updated_at } }
 *   PUT  { profile?, saved?, checklist? } → same shape
 *
 * The account id comes only from the verified session cookie, so a browser
 * can read and write its own account's data and nobody else's.
 */
import { NextResponse, type NextRequest } from "next/server";

import { AuthBackendError, accountData } from "@/lib/auth/backend";
import { currentUser, sameOrigin } from "@/lib/auth/server";

const MAX_BODY_BYTES = 900 * 1024;
const SECTIONS = ["profile", "saved", "checklist"] as const;

function errorResponse(err: unknown) {
  const status = err instanceof AuthBackendError ? err.status : 500;
  const message = err instanceof AuthBackendError ? err.message : "Couldn't sync.";
  return NextResponse.json({ error: message }, { status: status >= 400 ? status : 500 });
}

export async function GET() {
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  try {
    return NextResponse.json({ data: await accountData.get(user.id) }, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (err) {
    return errorResponse(err);
  }
}

export async function PUT(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });

  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) {
    return NextResponse.json({ error: "That's too much data to save." }, { status: 413 });
  }
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(text);
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }
  const sections: Record<string, unknown> = {};
  for (const key of SECTIONS) {
    if (key in body) sections[key] = body[key];
  }
  if (Object.keys(sections).length === 0) {
    return NextResponse.json({ error: "Nothing to save." }, { status: 422 });
  }
  try {
    return NextResponse.json({ data: await accountData.put(user.id, sections) });
  } catch (err) {
    return errorResponse(err);
  }
}
