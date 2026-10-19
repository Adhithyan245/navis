/**
 * /api/push/devices — the native app registers (PUT) or forgets (DELETE)
 * this phone's push token for the signed-in account.
 *   PUT    { token, platform: "android" | "ios" } → { prefs }
 *   DELETE { token }
 */
import { NextResponse, type NextRequest } from "next/server";

import { AuthBackendError } from "@/lib/auth/backend";
import { currentUser, sameOrigin } from "@/lib/auth/server";
import { pushBackend } from "@/lib/push/server";

function fail(err: unknown) {
  const status = err instanceof AuthBackendError ? err.status : 500;
  const message = err instanceof AuthBackendError ? err.message : "Something went wrong.";
  return NextResponse.json({ error: message }, { status: status >= 400 ? status : 500 });
}

async function readBody(request: NextRequest): Promise<Record<string, unknown> | null> {
  const text = await request.text();
  if (text.length > 8192) return null;
  try {
    const body = JSON.parse(text);
    return body && typeof body === "object" && !Array.isArray(body) ? body : null;
  } catch {
    return null;
  }
}

export async function PUT(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  const body = await readBody(request);
  const token = typeof body?.token === "string" ? body.token : "";
  const platform = body?.platform === "ios" ? "ios" : body?.platform === "android" ? "android" : null;
  if (!token || !platform) return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  try {
    return NextResponse.json(await pushBackend.registerDevice(user.id, token, platform));
  } catch (err) {
    return fail(err);
  }
}

export async function DELETE(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  const user = await currentUser();
  if (!user) return NextResponse.json({ ok: true });
  const body = await readBody(request);
  const token = typeof body?.token === "string" ? body.token : "";
  if (!token) return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  try {
    return NextResponse.json(await pushBackend.unregisterDevice(user.id, token));
  } catch (err) {
    return fail(err);
  }
}
