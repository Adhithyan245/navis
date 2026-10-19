import type { Metadata } from "next";
import Link from "next/link";

import { LegalPage, SUPPORT_EMAIL, Section } from "@/components/legal/LegalPage";

export const metadata: Metadata = { title: "Support" };

export default function SupportPage() {
  return (
    <LegalPage title="Help & support">
      <p>
        We&apos;re happy to help. Email{" "}
        <a href={`mailto:${SUPPORT_EMAIL}`} className="text-indigo-600 hover:underline dark:text-indigo-400">{SUPPORT_EMAIL}</a>{" "}
        and we&apos;ll reply as soon as we can.
      </p>
      <Section title="Common questions">
        <dl className="space-y-4">
          <div>
            <dt className="font-medium text-zinc-900 dark:text-zinc-100">How do I delete my account?</dt>
            <dd>
              In the app, open <Link href="/account" className="text-indigo-600 hover:underline dark:text-indigo-400">Account &amp; privacy</Link>{" "}
              and choose &ldquo;Delete account&rdquo;. It removes your account and everything synced to it right away.
              You can download a copy of your data first.
            </dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-900 dark:text-zinc-100">Navis can&apos;t find my location.</dt>
            <dd>Allow location for Navis in your phone&apos;s settings, or search for your area instead.</dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-900 dark:text-zinc-100">A place, number or event is wrong.</dt>
            <dd>Email us the details and we&apos;ll fix or report it to the data source.</dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-900 dark:text-zinc-100">I lost my phone. Can I sign out of it?</dt>
            <dd>Yes: sign in on another device, open Account &amp; privacy and choose &ldquo;Sign out everywhere&rdquo;.</dd>
          </div>
        </dl>
      </Section>
    </LegalPage>
  );
}
