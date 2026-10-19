"use client";
/**
 * DarkModeToggle — small icon button that flips the Tailwind dark class
 * on document.documentElement.
 *
 * Hydration-safe via `useSyncExternalStore`: the SSR/first-paint snapshot
 * is the deterministic "Moon icon, not yet mounted" state; after hydration,
 * React subscribes to a MutationObserver on the documentElement's class
 * list so the icon updates whenever the dark class flips.
 */
import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";

function subscribeDark(callback: () => void): () => void {
  if (typeof document === "undefined") return () => {};
  const obs = new MutationObserver(callback);
  obs.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
  return () => obs.disconnect();
}

function getDarkSnapshot(): boolean {
  if (typeof document === "undefined") return false;
  return document.documentElement.classList.contains("dark");
}

// `mounted` flips true on first post-hydration render — same SSR-safety
// pattern as ProfileContext / SavedItemsContext.
function noopSubscribe(): () => void {
  return () => {};
}

export function DarkModeToggle() {
  const mounted = useSyncExternalStore(noopSubscribe, () => true, () => false);
  const isDark = useSyncExternalStore(subscribeDark, getDarkSnapshot, () => false);

  const toggle = () => {
    if (typeof document === "undefined") return;
    document.documentElement.classList.toggle("dark", !isDark);
    try {
      // Read by the pre-paint script in app/layout.tsx.
      localStorage.setItem("navis_theme", isDark ? "light" : "dark");
    } catch {
      // Storage unavailable (private mode) — theme just won't persist.
    }
  };

  const label = !mounted ? "Toggle theme" : isDark ? "Light mode" : "Dark mode";

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={toggle}
      aria-label={label}
      title={label}
    >
      {mounted && isDark ? <Sun /> : <Moon />}
    </Button>
  );
}
