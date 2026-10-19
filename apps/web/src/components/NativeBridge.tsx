"use client";
/** Hooks the page into the Capacitor shell when it runs inside the app. */
import { useEffect } from "react";

import { initNativeShell } from "@/lib/native";

export function NativeBridge() {
  useEffect(() => initNativeShell(), []);
  return null;
}
