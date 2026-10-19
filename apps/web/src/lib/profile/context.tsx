"use client";
/**
 * ProfileContext — single source of truth for the persisted UserProfile.
 *
 * All consumers (OnboardingGate, OnboardingWizard, Profile page, useNavisQuery)
 * go through `useProfileContext`. The provider subscribes to localStorage
 * via `useSyncExternalStore` — React's canonical primitive for external
 * stores — which handles SSR snapshots and concurrent rendering correctly
 * without manual setState-in-effect cascades.
 *
 * Changes within the tab are broadcast via a custom event so multiple
 * consumers stay in sync; cross-tab changes are picked up via the native
 * `storage` event.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import type { UserProfile } from "./schema";
import {
  clearProfile as storageClear,
  getOnboardingDismissed,
  readProfile,
  setOnboardingDismissed,
  writeProfile,
} from "./storage";

export interface ProfileContextValue {
  /** True after the first post-hydration render; false during SSR + first paint. */
  ready: boolean;
  profile: UserProfile | null;
  onboardingDismissed: boolean;
  setProfile: (next: UserProfile) => void;
  clearProfile: () => void;
  dismissOnboarding: () => void;
  restoreOnboarding: () => void;
}

const STORAGE_EVENT = "navis:profile-changed";

const ProfileContext = createContext<ProfileContextValue | null>(null);

function subscribe(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(STORAGE_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(STORAGE_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

function dispatch(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(STORAGE_EVENT));
  }
}

// SSR/first-paint snapshots — kept hard-coded as `null` / `true` so the
// OnboardingGate's "show wizard" condition is always FALSE during pre-
// hydration (preventing a hydration mismatch when the wizard appears
// after storage is read).
const SSR_PROFILE: UserProfile | null = null;
const SSR_DISMISSED = true;
const SSR_READY = false;

const CLIENT_READY = true;

export function ProfileProvider({ children }: { children: ReactNode }) {
  const profile = useSyncExternalStore<UserProfile | null>(
    subscribe,
    readProfile,
    () => SSR_PROFILE
  );
  const dismissed = useSyncExternalStore<boolean>(
    subscribe,
    getOnboardingDismissed,
    () => SSR_DISMISSED
  );
  const ready = useSyncExternalStore<boolean>(
    subscribe,
    () => CLIENT_READY,
    () => SSR_READY
  );

  const setProfile = useCallback((next: UserProfile) => {
    writeProfile(next);
    setOnboardingDismissed(false);
    dispatch();
  }, []);

  const clearProfile = useCallback(() => {
    storageClear();
    setOnboardingDismissed(false);
    dispatch();
  }, []);

  const dismissOnboarding = useCallback(() => {
    setOnboardingDismissed(true);
    dispatch();
  }, []);

  const restoreOnboarding = useCallback(() => {
    setOnboardingDismissed(false);
    dispatch();
  }, []);

  const value = useMemo<ProfileContextValue>(
    () => ({
      ready,
      profile,
      onboardingDismissed: dismissed,
      setProfile,
      clearProfile,
      dismissOnboarding,
      restoreOnboarding,
    }),
    [ready, profile, dismissed, setProfile, clearProfile, dismissOnboarding, restoreOnboarding]
  );

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfileContext(): ProfileContextValue {
  const ctx = useContext(ProfileContext);
  if (!ctx) {
    throw new Error(
      "useProfileContext must be used within <ProfileProvider>. Mount it inside (main)/layout.tsx."
    );
  }
  return ctx;
}
