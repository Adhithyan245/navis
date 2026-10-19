/**
 * /api/push/prefs — which notifications the signed-in account gets.
 *   GET → { prefs: { safety_alerts, event_reminders, devices } }
 *   PUT { safety_alerts?: boolean, event_reminders?: boolean } → same
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

export async function GET() {
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  try {
    return NextResponse.json(await pushBackend.getPrefs(user.id), { headers: { "Cache-Control": "no-store" } });
  } catch (err) {
    return fail(err);
  }
}

export async function PUT(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  const changes: { safety_alerts?: boolean; event_reminders?: boolean } = {};
  if (typeof body?.safety_alerts === "boolean") changes.safety_alerts = body.safety_alerts;
  if (typeof body?.event_reminders === "boolean") changes.event_reminders = body.event_reminders;
  if (Object.keys(changes).length === 0) return NextResponse.json({ error: "Nothing to change." }, { status: 422 });
  try {
    return NextResponse.json(await pushBackend.setPrefs(user.id, changes));
  } catch (err) {
    return fail(err);
  }
}
