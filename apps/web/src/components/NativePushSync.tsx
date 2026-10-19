"use client";
/** Signed-in pages inside the native app: keep this phone's push token current. */
import { useEffect } from "react";

import { syncPushIfGranted } from "@/lib/push/native";

export function NativePushSync() {
  useEffect(() => {
    void syncPushIfGranted().catch(() => undefined);
  }, []);
  return null;
}
