/**
 * localStorage seam for UserProfile + onboarding-dismissed flag.
 *
 * SSR-safe: every function checks `typeof window` and returns the
 * "no-data" sentinel when called server-side.
 *
 * `readProfile()` is memoized against the raw localStorage string so
 * repeated calls during a render pass return a stable reference — this
 * is what `useSyncExternalStore` needs to avoid infinite re-renders.
 * The cache invalidates automatically whenever the underlying raw
 * value changes (write, clear, or another tab updating).
 */
import { scopedKey } from "@/lib/account/scope";
import { isLocation } from "@/lib/runtime/location";
import type { Location } from "@/lib/runtime/location";
import type { UserProfile } from "./schema";

function locOrUndef(v: unknown): Location | undefined {
  return isLocation(v) ? v : undefined;
}

const PROFILE_KEY   = "navis_user_profile_v1";
const DISMISSED_KEY = "navis_onboarding_dismissed_v1";

function safeLocalStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    // Private-browsing / disabled storage: return null and degrade gracefully.
    return null;
  }
}

// ── readProfile cache ──────────────────────────────────────────────────────
let _profileRaw: string | null | undefined = undefined;
let _profileSnapshot: UserProfile | null = null;

export function readProfile(): UserProfile | null {
  const ls = safeLocalStorage();
  if (!ls) return null;
  let raw: string | null;
  try {
    raw = ls.getItem(scopedKey(PROFILE_KEY));
  } catch {
    return null;
  }
  if (raw === _profileRaw) return _profileSnapshot;
  _profileRaw = raw;
  _profileSnapshot = raw ? parseProfile(raw) : null;
  return _profileSnapshot;
}

function parseProfile(raw: string): UserProfile | null {
  try {
    const parsed = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed.city === "string" &&
      typeof parsed.moveStage === "string" &&
      Array.isArray(parsed.interests)
    ) {
      // Tolerant rehydration: fill in any missing field (handles older
      // pre-extension blobs from before homeArea/budgetBand/goals existed).
      return {
        city: parsed.city,
        homeArea: typeof parsed.homeArea === "string" ? parsed.homeArea : "",
        moveStage: parsed.moveStage,
        household: typeof parsed.household === "string" ? parsed.household : "",
        workStyle: typeof parsed.workStyle === "string" ? parsed.workStyle : "",
        officeLocation:
          typeof parsed.officeLocation === "string" ? parsed.officeLocation : undefined,
        budgetBand: typeof parsed.budgetBand === "string" ? parsed.budgetBand : "",
        interests: parsed.interests.filter(
          (i: unknown): i is string => typeof i === "string"
        ),
        goals: Array.isArray(parsed.goals)
          ? parsed.goals.filter((g: unknown): g is string => typeof g === "string")
          : [],
        cityLocation: locOrUndef(parsed.cityLocation),
        homeAreaLocation: locOrUndef(parsed.homeAreaLocation),
        officeLocationResolved: locOrUndef(parsed.officeLocationResolved),
      };
    }
    return null;
  } catch {
    return null;
  }
}

export function writeProfile(profile: UserProfile): void {
  const ls = safeLocalStorage();
  if (!ls) return;
  try {
    ls.setItem(scopedKey(PROFILE_KEY), JSON.stringify(profile));
  } catch {
    /* quota or disabled — ignore */
  }
}

export function clearProfile(): void {
  const ls = safeLocalStorage();
  if (!ls) return;
  try {
    ls.removeItem(scopedKey(PROFILE_KEY));
  } catch {
    /* ignore */
  }
}

export function getOnboardingDismissed(): boolean {
  const ls = safeLocalStorage();
  if (!ls) return false;
  try {
    return ls.getItem(scopedKey(DISMISSED_KEY)) === "1";
  } catch {
    return false;
  }
}

export function setOnboardingDismissed(dismissed: boolean): void {
  const ls = safeLocalStorage();
  if (!ls) return;
  try {
    if (dismissed) ls.setItem(scopedKey(DISMISSED_KEY), "1");
    else ls.removeItem(scopedKey(DISMISSED_KEY));
  } catch {
    /* ignore */
  }
}
