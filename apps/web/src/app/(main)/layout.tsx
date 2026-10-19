import React from "react";
import { redirect } from "next/navigation";

import { AccountScope } from "@/components/AccountScope";
import { AppLayout } from "@/components/AppLayout";
import { NativePushSync } from "@/components/NativePushSync";
import { OnboardingGate } from "@/components/runtime/OnboardingGate";
import { ChecklistProvider } from "@/lib/checklist/context";
import { ProfileProvider } from "@/lib/profile/context";
import { SavedItemsProvider } from "@/lib/saved/context";
import { currentUser } from "@/lib/auth/server";

export default async function MainLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Authoritative check (proxy.ts only does an optimistic redirect): also
  // catches deleted accounts and sessions revoked by "sign out everywhere".
  const user = await currentUser();
  if (!user) redirect("/login");

  return (
    <AppLayout user={user}>
      <AccountScope userId={user.id}>
        <ProfileProvider>
          <SavedItemsProvider>
            <ChecklistProvider>
              <OnboardingGate>{children}</OnboardingGate>
              <NativePushSync />
            </ChecklistProvider>
          </SavedItemsProvider>
        </ProfileProvider>
      </AccountScope>
    </AppLayout>
  );
}

