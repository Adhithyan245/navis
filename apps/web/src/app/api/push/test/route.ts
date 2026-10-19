/** POST /api/push/test — send a test notification to the signed-in account's devices. */
import { NextResponse, type NextRequest } from "next/server";

import { currentUser, sameOrigin } from "@/lib/auth/server";
import { pushBackend } from "@/lib/push/server";

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  try {
    return NextResponse.json(await pushBackend.test(user.id));
  } catch {
    return NextResponse.json({ error: "We couldn't send a test right now." }, { status: 503 });
  }
}
