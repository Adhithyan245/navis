"use client";
/**
 * OnboardingGate — wraps page children and conditionally mounts the
 * onboarding wizard on first visit.
 *
 * SSR-safe: nothing is rendered until `ready` flips true on the client,
 * so server-rendered HTML never includes the modal. Same hydration-safe
 * pattern as DarkModeToggle.
 */
import type { ReactNode } from "react";

import { OnboardingWizard } from "@/components/runtime/OnboardingWizard";
import { useProfileContext } from "@/lib/profile/context";

export function OnboardingGate({ children }: { children: ReactNode }) {
  const { ready, profile, onboardingDismissed } = useProfileContext();
  const showWizard = ready && !profile && !onboardingDismissed;
  return (
    <>
      {children}
      {showWizard && <OnboardingWizard />}
    </>
  );
}
