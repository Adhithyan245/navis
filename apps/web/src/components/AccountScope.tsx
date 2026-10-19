"use client";
/**
 * AccountScope — points the local stores at the signed-in account's keys
 * (before they first read) and keeps them synced with the account's server
 * copy. Mounted once in (main)/layout.tsx around the store providers.
 */
import { useEffect } from "react";

import { setStorageScope } from "@/lib/account/scope";
import { startAccountSync } from "@/lib/account/sync";

export function AccountScope({ userId, children }: { userId: string; children: React.ReactNode }) {
  // Must happen during render, before the providers below take their first
  // snapshot; idempotent for the same id.
  setStorageScope(userId);

  useEffect(() => startAccountSync(), [userId]);

  return <>{children}</>;
}
