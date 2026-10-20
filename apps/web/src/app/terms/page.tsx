import type { Metadata } from "next";

import Link from "next/link";

import { COMPANY_NAME, LegalPage, SUPPORT_EMAIL, Section } from "@/components/legal/LegalPage";

export const metadata: Metadata = { title: "Terms of service" };

export default function TermsPage() {
  return (
    <LegalPage title="Terms of service" updated="October 20, 2026">
      <p>
        These terms cover your use of Navis, provided by {COMPANY_NAME}. By creating an account or using the app you
        agree to them and to our{" "}
        <Link href="/disclaimer" className="text-indigo-600 hover:underline dark:text-indigo-400">disclaimer</Link>,
        which is part of these terms.
      </p>
      <Section title="Using Navis">
        <p>
          You need to be at least 13 (or the minimum age in your country) to create an account. Keep your sign-in
          details safe; you&apos;re responsible for activity on your account. Don&apos;t misuse the service: no
          scraping, automated bulk requests, attempts to break security, or using it to harm others.
        </p>
      </Section>
      <Section title="Information in the app">
        <p>
          Navis brings together maps, directions, events, transit, health services, emergency numbers and local tips
          from many sources, some of them AI-generated and labelled as such. We work to keep it accurate, but places
          change: opening hours, prices, routes, event details and phone numbers can be out of date. Live transit
          positions and arrival times are estimates from operators&apos; public data feeds. Check important details
          with the official source before relying on them.
        </p>
        <p>
          <strong>Navis is not an emergency service</strong> and doesn&apos;t provide medical, legal or financial
          advice. In an emergency, call the local emergency number. Directions are guidance only: obey traffic laws
          and road signs, and use your own judgement.
        </p>
      </Section>
      <Section title="Third-party services">
        <p>
          Bookings, tickets and appointments happen on the provider&apos;s own website or app, under their terms.
          We aren&apos;t a party to those transactions.
        </p>
      </Section>
      <Section title="Your content">
        <p>
          What you save stays yours. You give us permission to store and process it only to run the service for you.
          You can delete it, or your whole account, at any time.
        </p>
      </Section>
      <Section title="Availability and changes">
        <p>
          We may change, pause or discontinue features. We may suspend accounts that break these terms. We&apos;ll
          post updated terms here; continuing to use Navis after a change means you accept it.
        </p>
      </Section>
      <Section title="Liability">
        <p>
          Navis is provided &ldquo;as is&rdquo;. To the extent the law allows, we aren&apos;t liable for indirect or
          consequential losses, or for losses caused by relying on third-party information. You use Navis at your own
          risk and are responsible for the decisions you make with it, and you agree to indemnify us against claims
          arising from your use or misuse of the service. Nothing here limits rights you have under consumer law that
          can&apos;t be waived.
        </p>
      </Section>
      <Section title="Contact">
        <p>
          <a href={`mailto:${SUPPORT_EMAIL}`} className="text-indigo-600 hover:underline dark:text-indigo-400">{SUPPORT_EMAIL}</a>
        </p>
      </Section>
    </LegalPage>
  );
}
