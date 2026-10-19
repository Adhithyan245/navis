/** GET /api/account/export — download everything Navis stores for this account (JSON). */
import { NextResponse } from "next/server";

import { authBackend } from "@/lib/auth/backend";
import { currentUser } from "@/lib/auth/server";

export async function GET() {
  const user = await currentUser();
  if (!user) return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  try {
    const data = await authBackend.exportAccount(user.id);
    return new NextResponse(JSON.stringify({ exported_at: new Date().toISOString(), ...data }, null, 2), {
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Disposition": 'attachment; filename="navis-account.json"',
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json({ error: "Export isn't available right now." }, { status: 503 });
  }
}
